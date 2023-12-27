import logging
import threading
from typing import Dict, List
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.chroma import ChromaCollection, ChromaDBManager, VectorRecordItem
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from memory_sdk.instance_memory_block.event_block import EventBlock, from_mongo_res_to_event_block
from memory_sdk.longterm_memory.long_term_mem_entity import LongTermMemoryEntity

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class LongTermMemoryMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            LongTermMemoryMgr._ready = True
            self.mongo_client = MongoDBClient()
            self.mem_map: Dict[str, LongTermMemoryEntity] = {}
            self.event_stash: Dict[str, List[EventBlock]] = {}

    def load_from_mongo(self, AID: str, target_id: str, entity: LongTermMemoryEntity):
        chroma_collection = ChromaDBManager().get_collection(gen_collection_name(AID, target_id))
        entity.set_collection(chroma_collection)
        mem_block_lst = self.mongo_client.find_from_collection("AI_memory_block",
                                                               filter={
                                                                   "$and": {
                                                                       "AID": AID,
                                                                       f'participant_ids.{target_id}': {
                                                                           '$exists': True},
                                                                   }
                                                               })
        logger.info(f"[LongTermMemoryEntity] load from mongo result number: {len(mem_block_lst)}")
        mem_blocks = [from_mongo_res_to_event_block(event_block) for event_block in mem_block_lst]
        entity.upload_new_mem_block(mem_blocks)
        entity.set_ready()
        logger.info(f"[LongTermMemoryEntity] load from mongo success")

    def _upload_collection_to_blob_and_delete(self, entity: LongTermMemoryEntity):
        ChromaDBManager().close_collection(entity.collection.get_collection_name(), True)

    def load_from_blob(self, entity_name: str, entity: LongTermMemoryEntity):
        collection = ChromaDBManager().get_collection(entity_name, use_cloud_if_not_exist=True)
        entity.set_collection(collection)
        entity.set_ready()
        logger.info(f"[LongTermMemoryEntity] load from blob success")

    def get_long_term_mem_entity(self, AID: str, target_id: str) -> LongTermMemoryEntity:
        store_key = gen_collection_name(AID, target_id)
        if store_key not in self.mem_map:
            entity = LongTermMemoryEntity(
                AID=AID,
                target_id=target_id,
            )
            self.mem_map[store_key] = entity

            def load_vector_collection():
                if ChromaDBManager().if_cloud_snapshot_exist(store_key):
                    self.load_from_blob(store_key, entity)
                else:
                    self.load_from_mongo(AID, target_id, entity)
            threading.Thread(target=load_vector_collection).start()
            return entity
        else:
            return self.mem_map[store_key]

    def update_event_block_for_entity(self, AID: str, target_id: str, block_lst: List[EventBlock]):
        store_key = gen_collection_name(AID, target_id)
        if store_key not in self.event_stash:
            self.event_stash[store_key] = block_lst
        else:
            self.event_stash[store_key].extend(block_lst)

    def close_long_term_entity(self, AID: str, target_id: str):
        store_key = gen_collection_name(AID, target_id)
        if store_key not in self.mem_map:
            return
        entity = self.mem_map[store_key]
        if store_key in self.event_stash:
            block_lst = self.event_stash[store_key]
            entity.upload_new_mem_block(block_lst)
            del self.event_stash[store_key]
        self._upload_collection_to_blob_and_delete(entity)
        del self.mem_map[store_key]
        return

    def __new__(cls, *args, **kwargs):
        if not hasattr(LongTermMemoryMgr, "_instance"):
            with LongTermMemoryMgr._instance_lock:
                if not hasattr(LongTermMemoryMgr, "_instance"):
                    LongTermMemoryMgr._instance = object.__new__(cls)
        return LongTermMemoryMgr._instance


def gen_collection_name(AID: str, target_id: str):
    return f"long_term_memory_{AID}_{target_id}"
