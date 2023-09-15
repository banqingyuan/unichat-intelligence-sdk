import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

from common_py.client.redis_client import RedisClient
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from memory_sdk.event_block.event_block_mgr import BlockManager
from memory_sdk.memory_entity import UserMemoryEntity

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class Hippocampus:

    def __init__(self, AID: str):
        self.redis_client = RedisClient()
        self.AID = AID
        self.memory_entities: Dict = {}
        self.block_mgr = BlockManager(AID)

    def load_memory_of_user(self, UID: str) -> Optional[UserMemoryEntity]:
        """
        加载记忆
        :param UID: 用户ID
        :return: bool 是否加载成功
        """
        try:
            if UID in self.memory_entities:
                return self.memory_entities[UID]
            entity = UserMemoryEntity(self.AID, UID, self.redis_client)
            self.memory_entities[UID] = entity
            return entity
        except Exception as e:
            logger.error(f'load memory of user error: {e}')
            return None

    def create_mem_block(self, event_slice: list):
        """
        创建记忆块
        :param event_slice: 事件列表
        """
        self.block_mgr.create(event_slice)

    def on_destroy(self):
        self.block_mgr.on_destroy(self.memory_entities)  # 和下面有先后顺序，不能一起销毁
        with ThreadPoolExecutor(max_workers=5) as executor:
            for entity in self.memory_entities.values():
                executor.submit(entity.on_destroy)
