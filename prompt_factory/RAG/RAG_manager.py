import datetime
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from memory_sdk.instance_memory_block.event_block import load_block_from_mongo
from memory_sdk.longterm_memory.long_term_mem_mgr import LongTermMemoryMgr
from prompt_factory.RAG.env_awareness import EnvRAGMgr
from prompt_factory.RAG.unichat_knowledge import KnowledgeMgr

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class RAGMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            RAGMgr._ready = True
            self.env_mgr = EnvRAGMgr()
            self.knowledge_mgr = KnowledgeMgr()

    def query_RAG(self, input_message: str, channel_name: str, AID: str, UID: str) -> str:
        try:
            # 这里内部只有一个io操作，可以先串行
            entity = LongTermMemoryMgr().get_long_term_mem_entity(AID, UID)
            topic_relevant_block_lst = entity.get_block_name_by_text_input(input_message, count=2)
            # 全量过llm太慢了，优化之后再上，优化方案可以首先过一遍预设的vector db
            # time_relevant_block_lst = entity.time_relevant_query(input_message, count=2)

            topic_task_lst = []
            time_task_lst = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                def get_summary_by_block_name(_block_name: str) -> (str, str):
                    block = load_block_from_mongo(_block_name)
                    if not block:
                        return ''
                    formatted_time = 'unknown'
                    block_create_time = block.create_timestamp
                    if block_create_time > 0:
                        formatted_time = datetime.datetime.fromtimestamp(block_create_time).strftime('%Y-%m-%d')
                    return block.get_summary(), formatted_time

                for block_name in topic_relevant_block_lst:
                    topic_task_lst.append(executor.submit(get_summary_by_block_name, block_name))
                # for block_name in time_relevant_block_lst:
                #     time_task_lst.append(executor.submit(get_summary_by_block_name, block_name))

            RAG_result = ''
            topic_summary = ''
            if len(topic_task_lst) > 0:
                topic_summary = "### Historical conversation data related to the current topic \n "
                summary_lst = []
                for summary_task in topic_task_lst:
                    summary, formatted_time = summary_task.result()
                    formatted_summary = f"Conversation happened in {formatted_time}: \n {summary}"
                    summary_lst.append(formatted_summary)
                topic_summary += '\n'.join(summary_lst)


            time_relevant_summary = ''
            if len(time_task_lst) > 0:
                time_relevant_summary = "### Memories related to times mentioned in conversations \n "
                summary_lst = []
                for summary_task in topic_task_lst:
                    summary, formatted_time = summary_task.result()
                    formatted_summary = f"Conversation happened in {formatted_time}: \n {summary}"
                    summary_lst.append(formatted_summary)
                time_relevant_summary += '\n'.join(summary_lst)

            env_str = self.env_mgr.env_getter(input_message, channel_name)
            knowledge_str = self.knowledge_mgr.query(input_message)

            if topic_summary:
                RAG_result += topic_summary + '\n'
            if time_relevant_summary:
                RAG_result += time_relevant_summary + '\n'
            if env_str:
                RAG_result += env_str + '\n'
            if knowledge_str:
                RAG_result += knowledge_str + '\n'
            return topic_summary
        except Exception as e:
            logger.exception(e)
            return ''

    def __new__(cls, *args, **kwargs):
        if not hasattr(RAGMgr, "_instance"):
            with RAGMgr._instance_lock:
                if not hasattr(RAGMgr, "_instance"):
                    RAGMgr._instance = object.__new__(cls)
        return RAGMgr._instance