import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from hashlib import md5
from typing import List

from common_py.client.azure_mongo import MongoDBClient
from common_py.client.chroma import ChromaCollection, ChromaDBManager, VectorRecordItem
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler

split_code = '*****'

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

CollectionName_Knowledge = "unichat_knowledge_collection"


class KnowledgeMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            KnowledgeMgr._ready = True
            self.mongo = MongoDBClient()
            self.check_sum = ''
            self.knowledge_vector_collection: ChromaCollection = ChromaDBManager().get_collection(CollectionName_Knowledge)
            self._refresh()

    def _refresh(self):
        try:
            results = self.mongo.find_from_collection("unichat_knowledge", filter={})

            knowledge_block = []
            raw_data = ''
            for res in results:
                knowledge_text = res.get("content", "")
                raw_data += knowledge_text
                knowledge_block.extend(knowledge_text.split(split_code))
            check_sum = md5(raw_data.encode()).hexdigest()
            if check_sum == self.check_sum:
                return
            query_results = self.knowledge_vector_collection.get(where={})
            if len(query_results) > 0:

                all_ids = [item.id for item in query_results]
                self.knowledge_vector_collection.delete(ids=all_ids)

            items = []
            for item in knowledge_block:
                items.append(VectorRecordItem(
                    id=str(uuid.uuid4()),
                    documents=item,
                    meta={
                      "corpus_text": item,
                    }
                ))
            self.knowledge_vector_collection.upsert_many(items)
            self.check_sum = check_sum
        except Exception as e:
            logger.exception(f"load knowledge failed: {e}")
            return
        finally:
            threading.Timer(5 * 60, self._refresh).start()

    def query(self, input_message: str) -> str:
        results = self.knowledge_vector_collection.query(input_data=input_message, meta_filter={}, top_k=3, threshold=0.6)

        info_tpl = "Provided are potential references about the App: \n {app_knowledge}\n Evaluate their relevancy. You may inform the user their query is unsupported or in development if the info is insufficient."
        knowledge_block = []
        for item in results:
            knowledge_block.append(item.documents)
        if len(knowledge_block) == 0:
            return ''
        app_knowledge = '\n'.join(knowledge_block)
        return info_tpl.format(app_knowledge=app_knowledge)

    def __new__(cls, *args, **kwargs):
        if not hasattr(KnowledgeMgr, "_instance"):
            with KnowledgeMgr._instance_lock:
                if not hasattr(KnowledgeMgr, "_instance"):
                    KnowledgeMgr._instance = object.__new__(cls)
        return KnowledgeMgr._instance