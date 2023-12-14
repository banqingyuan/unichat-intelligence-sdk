import logging
import threading

from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

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

    def query_RAG(self, input_message: str, channel_name) -> str:
        try:
            env_str = self.env_mgr.env_getter(input_message, channel_name)
            knowledge_str = self.knowledge_mgr.query(input_message)
            return env_str + '\n' + knowledge_str
        except Exception as e:
            logger.exception(e)
            return ''

    def __new__(cls, *args, **kwargs):
        if not hasattr(RAGMgr, "_instance"):
            with RAGMgr._instance_lock:
                if not hasattr(RAGMgr, "_instance"):
                    RAGMgr._instance = object.__new__(cls)
        return RAGMgr._instance