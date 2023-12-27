import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from common_py.ai_toolkit.openAI import ChatGPTClient, Message
from common_py.client.chroma import ChromaCollection, VectorRecordItem
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from memory_sdk.const import gen_question_answer
from memory_sdk.instance_memory_block.event_block import EventBlock, load_event_block_by_name

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class LongTermMemoryEntity:

    def __init__(self, AID: str, target_id: str, chroma_collection: ChromaCollection = None):
        self.AID = AID
        self.target_id = target_id
        self.collection: Optional[ChromaCollection] = chroma_collection
        self.LLMClient = ChatGPTClient()
        self.ready: bool = False

    def set_collection(self, collection: ChromaCollection):
        self.collection = collection

    def set_ready(self):
        self.ready = True

    def upload_new_mem_block(self, mem_block_lst: List[EventBlock]):
        record_lst = []
        question_tasks = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            for mem_block in mem_block_lst:
                meta_data = {
                    "AID": self.AID,
                    "target_id": self.target_id,
                    "create_time": mem_block.create_timestamp,
                    "block_name": mem_block.name
                }
                task = executor.submit(self._gen_vector_index_from_mem_block, mem_block)
                question_tasks.append((meta_data, task))
        for tup in question_tasks:
            meta_data, task = tup
            questions = task.result()
            for question in questions:
                record_lst.append(VectorRecordItem(
                    id=str(uuid.uuid4()),
                    meta=meta_data,
                    documents=question
                ))
            record_lst.append(
                VectorRecordItem(
                    id=str(uuid.uuid4()),
                    meta=meta_data,
                    document=mem_block.raw_summary
                )
            )
        self.collection.upsert_many(record_lst)

    def _gen_vector_index_from_mem_block(self, mem_block: EventBlock) -> List[str]:
        chat_summary = mem_block.raw_summary
        question_num = 1
        if len(chat_summary) > 250:
            question_num = 2
        if len(chat_summary) > 500:
            question_num = 3
        question_index = []
        for i in range(3):
            try:
                gen_question_prompt = gen_question_answer.format(question_number=question_num,
                                                                 chat_summary=chat_summary)
                resp = self.LLMClient.generate(messages=[
                    Message(role='system', content=gen_question_prompt)
                ])
                if resp:
                    json_resp = json.loads(resp.get_chat_content())
                    if 'questions' not in json_resp or not isinstance(json_resp['questions'], list):
                        raise Exception(f"llm response expect questions key in json but not found: {json_resp}")
                    question_index.extend(json_resp['questions'])
                    break
            except Exception as e:
                logger.warning(f"gen vector index from mem block error: {e}")
                continue
        return question_index

    def get_block_name_by_time_range(self, start_time: int, end_time: int, content: str = None, count: int = 2) -> List[str]:
        if not self.ready:
            logger.warning(f"LongTermMemoryEntity not ready, return empty list")
            return []
        if not content:
            query_res = self.collection.get(where={
                "$and": [
                    {"create_time": {"$gte": start_time}},
                    {"create_time": {"$lte": end_time}},
                ]
            }, limit=count*4)
            self._get_unique_block_name(query_res, count)
        else:
            query_res = self.collection.query(input_data=content, meta_filter={
                "$and": [
                    {"create_time": {"$gte": start_time}},
                    {"create_time": {"$lte": end_time}},
                ]
            }, top_k=count*4, threshold=0.7)
            return self._get_unique_block_name(query_res, count)

    def get_block_name_by_text_input(self, content: str, count: int = 3) -> List[str]:
        if not self.ready:
            logger.warning(f"LongTermMemoryEntity not ready, return empty list")
            return []
        # 每个 summary 会生成四条query_index, count * 4是为了限制返回的最大数量。同时为了保证结果的多样性，不能让 top_k == count
        query_res = self.collection.query(input_data=content, meta_filter={}, top_k=count*4, threshold=0.7)
        return self._get_unique_block_name(query_res, count)

    def _get_unique_block_name(self, query_res: List[VectorRecordItem], count: int) -> List[str]:
        block_name_dict = {}
        for res in query_res:
            block_name = res.meta.get('block_name', None)
            if not block_name:
                logger.error(f"block name not found in meta: {res.json()}")
                continue
            block_name_dict[block_name] = res.score

        # get top count block name
        if len(block_name_dict) <= count:
            block_name_lst = list(block_name_dict.keys())
        else:
            block_name_lst = sorted(block_name_dict, key=lambda x: block_name_dict[x], reverse=True)[:count]

        return block_name_lst



