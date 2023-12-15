import calendar
import logging
from datetime import datetime, timezone, timedelta

from common_py.dto.room_info import RoomInfoMgr
from common_py.utils.channel.util import get_room_id_from_channel
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler
import threading
import uuid
from typing import Dict

from common_py.client.chroma import ChromaCollection, ChromaDBManager, VectorRecordItem

from prompt_factory.RAG.base import BaseInfoGetter, InfoType_Scene

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)
CollectionName_Env_RAG = "RAG_env_collection"


class EnvGetCurrentTime(BaseInfoGetter):

    corpus_text = [
        "What time is it now",
        "How many days until Christmas"
    ]
    info_type = InfoType_Scene

    def __call__(self, **kwargs):
        # 获取带时区信息的格式化时间
        today = datetime.now(timezone(timedelta(hours=0))).today()
        day_of_week = calendar.day_name[today.weekday()]

        system_prompt = "The current time is {formatted_time}."
        formatted_time = datetime.now(timezone(timedelta(hours=0))).strftime("%Y-%m-%d %H:%M:%S %z") + f" ({day_of_week})"
        return system_prompt.format(formatted_time=formatted_time)


class EnvGetCurrentRoomPlayer(BaseInfoGetter):

    corpus_text = [
        "Who is in the room",
        "Do you know who is",
        "How many people are in the room"
    ]
    info_type = InfoType_Scene

    def __call__(self, **kwargs):
        # both player and AIs
        try:
            channel_name = kwargs.get('channel_name', '')
            room_id = get_room_id_from_channel(channel_name)
            if len(room_id) == 0:
                return ''
            room_info = RoomInfoMgr().get_room_info(room_id=room_id)
            if room_info is None:
                return ''
            player_description = "Here is the list of players in the room:\n"
            play_lst = room_info.playerList
            for player in play_lst:
                player_description += f"{player.objectDisplayName}: {player.objectDescription}\n"
            for AI in room_info.AICharacterList:
                player_description += f"{AI.objectDisplayName}: {AI.objectDescription}\n"
            return player_description
        except Exception as e:
            logger.exception(e)
            return ''


EnvInfoGetterList = [
    EnvGetCurrentRoomPlayer(),
    EnvGetCurrentTime()
]


class EnvRAGMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            EnvRAGMgr._ready = True
            self._getter_dict: Dict[str, BaseInfoGetter] = {}
            self._env_getter_vector_collection: ChromaCollection = ChromaDBManager().get_collection(CollectionName_Env_RAG)
            for env_info_getter in EnvInfoGetterList:
                self._register_getter(env_info_getter)

    def _register_getter(self, info_getter: BaseInfoGetter):
        getter_name = info_getter.__class__.__name__
        self._getter_dict[getter_name] = info_getter
        for corpus_text in info_getter.corpus_text:
            self._env_getter_vector_collection.upsert_many([VectorRecordItem(
                id=str(uuid.uuid4()),
                documents=corpus_text,
                meta={
                    "getter_name": getter_name,
                    "getter_type": info_getter.info_type,
                    "corpus_text": corpus_text
                }
            )])

    def env_getter(self, input_message: str, channel_name) -> str:
        results = self._env_getter_vector_collection.query(input_data=input_message, meta_filter={
            "getter_type": InfoType_Scene
        }, top_k=3, threshold=0.6)

        getter_dict = {}
        for item in results:
            getter_name = item.meta.get("getter_name", None)
            if getter_name:
                getter = self._getter_dict.get(getter_name, None)
                if getter:
                    getter_dict[getter_name] = getter

        system_prompt = "Here is additional information about the current scene:\n {env_addition_info}"
        if len(getter_dict) > 0:
            env_addition_info = '\n'.join(
                [getter(**{'channel_name': channel_name}) for getter in getter_dict.values()]
            )
            return system_prompt.format(env_addition_info=env_addition_info)
        return ''

    def __new__(cls, *args, **kwargs):
        if not hasattr(EnvRAGMgr, "_instance"):
            with EnvRAGMgr._instance_lock:
                if not hasattr(EnvRAGMgr, "_instance"):
                    EnvRAGMgr._instance = object.__new__(cls)
        return EnvRAGMgr._instance


if __name__ == '__main__':
    print(EnvGetCurrentTime()())