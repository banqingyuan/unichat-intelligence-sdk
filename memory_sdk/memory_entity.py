import logging
import time
from typing import Optional

from common_py.client.azure_mongo import MongoDBClient
from common_py.client.redis_client import RedisClient, RedisAIMemoryInfo
from common_py.const.ai_attr import Entity_type_AI, Entity_type_user
from common_py.dto.user import UserInfoMgr
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from memory_sdk.util import seconds_to_english_readable

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

AI_memory_source_id = "source_id"
AI_memory_target_id = "target_id"
AI_memory_target_type = "target_type"
AI_memory_intimacy_point = "intimacy_point"
AI_memory_intimacy_level = "intimacy_level"
AI_memory_target_nickname = "target_nickname"
AI_memory_met_times = "met_times"
AI_memory_last_met_timestamp = "last_met_timestamp"
AI_memory_topic_mentioned_last_time = "topic_mentioned_last_time"
AI_memory_time_since_last_met_description = "time_since_last_met_description"
AI_memory_time_duration_since_last_met = "time_duration_since_last_met"


class UserMemoryEntity:
    """
    关于时间问题
    redis统一以时间戳格式存放，格式化时间的存取在python结构中处理。
    由于是服务器统一处理时间，对于各地的本地化时间处理复杂，所以尽量淡化绝对时间
    尽可能的使用相对时间，如：几天前，几分钟前，几小时前等

    # todo 是否在这里记录上次聊天的话题
    """

    def __init__(self, AID: str, target_id: str, target_type: str):
        self.redis_client = RedisClient()
        self.mongo_client = MongoDBClient()
        self.target_id = target_id
        self.AID = AID

        self.target_type = target_type if target_type == Entity_type_AI else Entity_type_user

        self.user_is_owner = True if self.AID.startswith(f"{self.target_id}-") else False
        self.met_times = 0
        self.target_nickname = ''
        self.time_since_last_met_description: Optional[str] = None  # 距离上次见面的自然语言描述 比如 1 year and 2 months ago
        self.time_duration_since_last_met: Optional[int] = None  # 距离上次见面的时间间隔，单位秒
        self.last_met_timestamp: Optional[int] = None  # 上次见面的时间戳
        self.topic_mentioned_last_time: Optional[str] = None  # 上次提到的话题

        self.current_stash: dict = {}  # 本次对话的暂存
        self.load_memory()

    def load_memory(self):
        """
        加载AI对某个人【或者AI】的记忆
        不要放写操作
        """
        result = self.redis_client.hgetall(RedisAIMemoryInfo.format(source_id=self.AID, target_id=self.target_id))
        if result is None:
            logger.warning(f"AIInstanceInfo with id {self.AID} not found, try to load from mongo")
            result = self._load_from_mongo()
            if result is None:
                logger.warning(f"AIInstanceInfo with id {self.AID} not found")
                return
            # assure the result is a Dict[str, str]
            self.redis_client.hset(RedisAIMemoryInfo.format(source_id=self.AID, target_id=self.target_id), result)

        result = {k.decode(): v.decode() for k, v in result.items()}

        self.met_times = int(result.get(AI_memory_met_times, 0))
        self.target_nickname = result.get(AI_memory_target_nickname, '')

        self.last_met_timestamp = int(result.get(AI_memory_last_met_timestamp, 0))
        if self.last_met_timestamp > 0:
            self.time_duration_since_last_met = int(time.time()) - self.last_met_timestamp
            self.time_since_last_met_description = seconds_to_english_readable(self.time_duration_since_last_met)

        self.topic_mentioned_last_time = result.get(AI_memory_topic_mentioned_last_time, None)

    def init_entity(self):
        # 要防止在加载失败时误初始化导致的数据丢失, 不要做破坏性的数据写入
        if self.target_type == Entity_type_user:
            user_info = UserInfoMgr().get_instance_info(self.target_id)
            self.target_nickname = user_info.name
            self.redis_client.hset(RedisAIMemoryInfo.format(source_id=self.AID, target_id=self.target_id), {
                AI_memory_source_id: self.AID,
                AI_memory_target_id: self.target_id,
                AI_memory_target_type: self.target_type,
                AI_memory_target_nickname: self.target_nickname
            })


    def _load_from_mongo(self):
        filter = {
            "source_id": self.AID,
            "target_id": self.target_id,
            "target_type": self.target_type,
        }
        res = self.mongo_client.find_one_from_collection("AI_memory_reflection", filter)
        if res is None:
            return None
        return res

    def element_stash(self, key: str, value: str):
        self.current_stash[key] = value

    def get_dict(self):
        return {
            AI_memory_met_times: self.met_times,
            AI_memory_last_met_timestamp: self.last_met_timestamp,
            AI_memory_time_since_last_met_description: self.time_since_last_met_description,
            AI_memory_time_duration_since_last_met: self.time_duration_since_last_met,
            AI_memory_topic_mentioned_last_time: self.topic_mentioned_last_time,
            AI_memory_target_id: self.target_id,
            AI_memory_target_type: self.target_type,
            AI_memory_source_id: self.AID,
        }

    def save_stash(self):
        self.redis_client.hset(RedisAIMemoryInfo.format(source_id=self.AID, target_id=self.target_id), self.current_stash)
        filter = {
            "source_id": self.AID,
            "target_id": self.target_id,
            "target_type": self.target_type,
        }
        res = self.mongo_client.update_many_document("AI_memory_reflection", filter, self.current_stash, False)
        self.current_stash = {}
        logger.info(f"save stash result: {res}")

    def refresh_memory(self):
        """
        与AI见面后的固定记忆刷新
        """

        self.met_times += 1
        self.element_stash(AI_memory_met_times, str(self.met_times))
        self.last_met_timestamp = int(time.time())
        self.element_stash(AI_memory_last_met_timestamp, str(self.last_met_timestamp))

        self.redis_client.hset(RedisAIMemoryInfo.format(source_id=self.AID, target_id=self.target_id),
                               self.current_stash)
        filter = {
            "source_id": self.AID,
            "target_id": self.target_id,
            "target_type": self.target_type,
        }
        user_entity = self.redis_client.hgetall(RedisAIMemoryInfo.format(source_id=self.AID, target_id=self.target_id))
        if user_entity is not None:
            partition_key = f"{self.AID}-{self.target_id}"
            user_entity['_partition_key'] = partition_key
            res = self.mongo_client.update_many_document("AI_memory_reflection", filter, user_entity, True)
            logger.info(f"create AI_memory_reflection {res.__str__()}")
        self.current_stash = {}






# if __name__ == '__main__':
#     ad = {
#         "a": "2",
#     }
#     dct = {
#         "a": "1",
#         **ad
#     }
#     print(dct)

