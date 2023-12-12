import threading
import time
from typing import List, Type
from common_py.ai_toolkit.openAI import Message
from common_py.model.base import BaseEvent
from memory_sdk.hippocampus import HippocampusMgr
import logging
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

EventType_badcase_retry = "badcase_retry"
EventType_conversation = "conversation"
EventType_scene_event = 'scene_event'
EventType_say_hello = "say_hello"  # deprecated


class MemoryManager:

    def __init__(self, AID: str, close_signal: threading.Event):
        self.hippocampus = HippocampusMgr().get_hippocampus(AID)
        self.local_event_buffer: List[BaseEvent] = []

        # 用于记录zip_context_memory的索引
        self.zip_index: int = -1
        self.close_event: threading.Event = close_signal
        # self.system_prompt_key: str = "system_prompt"
        # self.local_chat_buffer_key: str = "chat_history"
        # self.current_message_key: str = "input_message"

    def add_event(self, event: BaseEvent):
        self.local_event_buffer.append(event)
        # if isinstance(event, ConversationEvent):
        #     if event.role == 'user':
        #         self.local_chat_buffer.append(Message(role='user', content=event.message))
        #     elif event.role == 'AI':
        #         self.local_chat_buffer.append(Message(role='assistant', content=event.message))
        #     elif event.role == 'system':
        #         self.local_chat_buffer.append(Message(role='system', content=event.message))
        # elif isinstance(event, InnerVoiceEvent):
        #     self.local_chat_buffer.append(Message(role='system', content=event.message))

    def get_message_list(self, count: int = 15) -> List[Message]:
        if len(self.local_event_buffer) < count:
            return [e.get_message_from_event() for e in self.local_event_buffer]
        else:
            return [e.get_message_from_event() for e in self.local_event_buffer[-count:]]

    def get_event_list(self, target_type: Type[BaseEvent], count: int = 15) -> List[BaseEvent]:
        # get the last count events of target_type
        if len(self.local_event_buffer) < count:
            return [e for e in self.local_event_buffer if isinstance(e, target_type)]
        else:
            target_event_lst = []
            for e in self.local_event_buffer[::-1]:
                if isinstance(e, target_type):
                    target_event_lst.append(e)
                    if len(target_event_lst) >= count:
                        break
            target_event_lst.reverse()
            return target_event_lst

    def zip_context_memory(self):
        try:
            while True:
                if self.close_event.is_set():
                    if len(list(
                            filter(lambda x: x.event_source == "conversation",
                                   self.local_event_buffer[self.zip_index + 1:]))) >= 4:
                        self.hippocampus.create_mem_block(self.local_event_buffer[self.zip_index + 1:])
                    return
                time.sleep(5)
                # 倒序遍历 local_event_buffer，查看最后一次会话的发生时间，如果是在一分钟前，就截断这个区间的数据，总结成一个block
                buffer_length = len(self.local_event_buffer)
                for idx in range(buffer_length - 1, self.zip_index, -1):
                    event = self.local_event_buffer[idx]
                    if event.event_source != "conversation":
                        continue
                    # summary and send to pinecone then clear local_event_buffer
                    if int(time.time()) - int(event.occur_time) > 60:
                        # 双重条件，当连续一分钟没有产生对话，并且连续的对话超过10句时，才作为一个block缓存
                        if len(list(filter(lambda x: x.event_source == "conversation",
                                           self.local_event_buffer[self.zip_index + 1:]))) > 10:
                            self.hippocampus.create_mem_block(self.local_event_buffer[self.zip_index + 1:])
                            self.zip_index = buffer_length - 1
                    break
        except Exception as e:
            logger.exception(e)
            return
        finally:
            logger.debug(f"zip context memory task has been stopped.")
            self.close_event.set()

    # def _data_collector(self, speaker_id: str, speak_content: str) -> Dict[str, Any]:
    #     """Collect data from inputs."""
    #
    #     with ThreadPoolExecutor(max_workers=2) as executor:
    #         speaker_info_future = executor.submit(self._get_user_info, speaker_id)
    #     speaker_info: UserBasicInformation = speaker_info_future.result()
    #     speaker_name = speaker_info.name
    #     current_message = f'[{speaker_name}:] {speak_content}' if speaker_name != "" else speak_content
    #     # current_message = speak_content
    #     return {
    #         "current_message": current_message,
    #     }
