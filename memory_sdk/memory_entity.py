import logging
import time
from typing import Optional

from common_py.client.redis_client import RedisClient, RedisAIMemoryInfo
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from memory_sdk.util import seconds_to_english_readable

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class UserMemoryEntity:
    """
    关于时间问题
    redis统一以时间戳格式存放，格式化时间的存取在python结构中处理。
    由于是服务器统一处理时间，对于各地的本地化时间处理复杂，所以尽量淡化绝对时间
    尽可能的使用相对时间，如：几天前，几分钟前，几小时前等

    # todo 是否在这里记录上次聊天的话题
    """
    keys_of_user_memory = ['met_times', 'last_met_timestamp', 'topic_mentioned_last_time', 'time_since_last_met_description', 'time_duration_since_last_met']

    def __init__(self, AID: str, UID: str, redis_client: RedisClient):
        self.redis_client = redis_client
        self.UID = UID
        self.AID = AID

        self.user_is_owner = True if self.AID.startswith(f"{self.UID}-") else False
        self.met_times = 0
        self.time_since_last_met_description: Optional[str] = None  # 距离上次见面的自然语言描述 比如 1 year and 2 months ago
        self.time_duration_since_last_met: Optional[int] = None  # 距离上次见面的时间间隔，单位秒
        self.last_met_timestamp: Optional[int] = None  # 上次见面的时间戳

        self.topic_mentioned_last_time: Optional[str] = None  # 上次提到的话题

        self.current_stash: dict = {}  # 本次对话的暂存
        self.load_memory()

    def load_memory(self):
        result = self.redis_client.hgetall(f"{RedisAIMemoryInfo}{self.AID}:{self.UID}")
        if result is None:
            logger.warning(f"AIInstanceInfo with id {self.AID} not found")
            return
        result = {k.decode(): v.decode() for k, v in result.items()}

        self.met_times = int(result.get('met_times', 0))

        self.last_met_timestamp = int(result.get('last_met_timestamp', 0))
        if self.last_met_timestamp > 0:
            self.time_duration_since_last_met = int(time.time()) - self.last_met_timestamp
            self.time_since_last_met_description = seconds_to_english_readable(self.time_duration_since_last_met)

        self.topic_mentioned_last_time = result.get('topic_mentioned_last_time', None)

        # 每次加载时重置topic_mentioned_last_time,
        # because this time is the last time of next time
        self.element_stash('topic_mentioned_last_time', '')

    def element_stash(self, key: str, value: str):
        self.current_stash[key] = value

    def get_dict(self):
        return {
            'met_times': self.met_times,
            'last_met_timestamp': self.last_met_timestamp,
            'time_since_last_met_description': self.time_since_last_met_description,
            'time_duration_since_last_met': self.time_duration_since_last_met,
            'topic_mentioned_last_time': self.topic_mentioned_last_time,
        }

    def on_destroy(self):
        self.met_times += 1
        self.last_met_timestamp = int(time.time())
        refresh_keys = {
            'met_times': self.met_times,
            'last_met_timestamp': self.last_met_timestamp,
            **self.current_stash
        }
        self.redis_client.hset(f"{RedisAIMemoryInfo}{self.AID}:{self.UID}", refresh_keys)
