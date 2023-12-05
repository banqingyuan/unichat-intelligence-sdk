import threading

from common_py.client.azure_mongo import MongoDBClient

from memory_sdk.event_block import EventBlock


class Funcs:

    _instance_lock = threading.Lock()

    def load_block_from_mongo(self, block_name: str) -> EventBlock:
        mongo_client = MongoDBClient()
        res = mongo_client.find_one_from_collection('AI_memory_block', {'name': block_name})
        if not res:
            raise Exception(f"can not find block: {block_name}")
        del res['origin_event']
        block = EventBlock(**res)
        return block

    def __new__(cls, *args, **kwargs):
        if not hasattr(Funcs, "_instance"):
            with Funcs._instance_lock:
                if not hasattr(Funcs, "_instance"):
                    Funcs._instance = object.__new__(cls)
        return Funcs._instance