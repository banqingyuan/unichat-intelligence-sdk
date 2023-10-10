import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, List

from common_py.const.ai_attr import Entity_type_user, AI_type_npc, Entity_type_AI
from common_py.dto.ai_instance import InstanceMgr
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from memory_sdk.event_block import BlockManager
from memory_sdk.memory_entity import UserMemoryEntity


logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class Hippocampus:

    def __init__(self, AID: str):
        self.AID = AID
        self.memory_entities: Dict = {}
        self.block_mgr = BlockManager(AID)

    def load_memory_of_user(self, UID: str, need_refresh: bool = False) -> Optional[UserMemoryEntity]:
        """
        加载记忆
        :param UID: 用户ID
        :return: bool 是否加载成功
        """
        try:
            if UID in self.memory_entities or not need_refresh:
                return self.memory_entities[UID]
            entity = UserMemoryEntity(self.AID, UID, Entity_type_user)
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


class HippocampusMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            HippocampusMgr._ready = True
            self.hippocampus: Dict[str, Hippocampus] = {}

    def get_hippocampus(self, AID: str) -> Optional[Hippocampus]:
        """
        获取海马体
        """
        try:
            if AID in self.hippocampus:
                return self.hippocampus[AID]
            else:
                InstanceMgr()
                hippocampus = Hippocampus(AID)
                self.hippocampus[AID] = hippocampus
                return hippocampus
        except Exception as e:
            logger.error(f'get hippocampus error: {e}')
            return None

    def destroy(self, AID: str):
        """
        销毁
        """
        try:
            if AID in self.hippocampus:
                self.hippocampus[AID].on_destroy()
                del self.hippocampus[AID]
        except Exception as e:
            logger.error(f'destroy error: {e}')

    def __new__(cls, *args, **kwargs):
        if not hasattr(HippocampusMgr, "_instance"):
            with HippocampusMgr._instance_lock:
                if not hasattr(HippocampusMgr, "_instance"):
                    HippocampusMgr._instance = object.__new__(cls)
        return HippocampusMgr._instance


def _gen_block_list_key(AID: str) -> str:

    h = hash(AID)
    # 分片到0-23小时，分段处理
    partition = str(h % 24)
    return f"AI_memory_block_list_{partition}_{AID}"