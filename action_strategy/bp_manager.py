import logging
import queue
import threading
from typing import Optional

from common_py.client.azure_mongo import MongoDBClient
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from action_strategy.bp_instance import BluePrintInstance

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class BluePrintManager:
    _instance_lock = threading.Lock()

    def __init__(self):
        self.mongo_client: MongoDBClient = MongoDBClient()
        all_bp_script = self.mongo_client.find_from_collection("AI_blue_print", filter={})
        self.bp_collection = {}
        for bp_script in all_bp_script:
            if 'name' in bp_script:
                # todo 补充有效性检查
                self.bp_collection[bp_script['name']] = bp_script

    def get_instance(self, bp_name: str, q: queue.Queue) -> Optional[BluePrintInstance]:
        try:
            return BluePrintInstance(q, self.bp_collection[bp_name])
        except Exception as e:
            logger.exception(e)
            return None

    def __new__(cls, *args, **kwargs):
        if not hasattr(BluePrintManager, "_instance"):
            with BluePrintManager._instance_lock:
                if not hasattr(BluePrintManager, "_instance"):
                    BluePrintManager._instance = object.__new__(cls)
        return BluePrintManager._instance
