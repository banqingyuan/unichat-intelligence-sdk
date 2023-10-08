import json
import logging
import time
from typing import List, Dict

from common_py.ai_toolkit.openAI import ChatGPTClient, Message
from common_py.model.base import BaseEvent
from common_py.model.chat import ConversationEvent

from common_py.client.embedding import OpenAIEmbedding
from pydantic import BaseModel

from memory_sdk import const
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from memory_sdk.hippocampus import HippocampusMgr

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class EventBlock(BaseModel):
    origin_event: List[BaseEvent] = []
    AID: str = ""
    name: str = ""
    summary: str = ""

    participant_ids: Dict[str, str] = {}
    participants: List[str] = []
    tags: List[str] = []
    create_timestamp: int = "0"
    last_active_timestamp: int = "0"
    embedding_1536D: List[float] = []
    tags_embedding_1536D: List[float] = []
    importance: int = 0

    # top3_similar_block: List[Tuple[str, float]] = []

    def build_from_dialogue_event(self, event_list: List[BaseEvent]):
        if len(event_list) == 0:
            raise Exception("Event list is empty")
        self.origin_event = event_list
        self.create_timestamp = int(time.time())
        for event in self.origin_event:
            if isinstance(event, ConversationEvent):
                # AI 也算参与者
                # if event.role.lower() == 'ai':
                #     continue
                self.participant_ids[event.speaker] = event.speaker_name
        self.last_active_timestamp = int(time.time())
        self.name = self._build_name()
        self._summarize()

    def _summarize(self):
        zipped_text = self._zip_event_log()
        if zipped_text == "":
            raise Exception("Event log is empty")
        logger.debug(f"zipped_text: {zipped_text}")
        messages = [
            Message(role="system", content=const.summary_tpl),
            Message(role="user", content=const.few_shot_user),
            Message(role="assistant", content=const.few_shot_assistant),
            Message(role="user", content=zipped_text),
        ]
        response = ChatGPTClient(temperature=0).generate(messages=messages)
        try:
            extract_content = json.loads(response.get_chat_content())
        except Exception:
            messages.append(Message(role="system", content="Your output must be valid json"))
            response = ChatGPTClient(temperature=0).generate(messages=messages)
            try:
                extract_content = json.loads(response.get_chat_content())
            except Exception:
                logger.error(f"llm can not extract a valued json, content: {response.get_chat_content()}")
                raise Exception("llm can not extract a valued json")
        if "summary" not in extract_content or \
                "tags" not in extract_content or \
                "participants" not in extract_content:
            raise Exception(f"llm can not extract expect struct but content: {extract_content}")
        chatting_speaker = {}
        for event in self.origin_event:
            if isinstance(event, ConversationEvent):
                chatting_speaker[event.speaker] = event.speaker_name
        replaced_summary = extract_content["summary"]
        if len(chatting_speaker) > 0 :
            speaker_name_to_id = ""
            example_username = list(chatting_speaker.keys())[0]
            example_UID = chatting_speaker[example_username]
            for name, id in chatting_speaker.items():
                speaker_name_to_id += f"username {name} with id: {id} \n"
            summary_response = ChatGPTClient(temperature=0).generate(messages=
            [
                Message(role="system", content=const.change_name_to_id.format(example_username=example_username, example_UID=example_UID) + speaker_name_to_id),
            ]
            )

            replaced_summary = summary_response.get_chat_content()


        self.tags = extract_content["tags"]
        self.participants = extract_content["participants"]
        self.summary = replaced_summary
        logger.debug(f"summary result: {self.summary}")
        embedding = OpenAIEmbedding()
        self.embedding_1536D = embedding(input=self.summary)
        self.tags_embedding_1536D = embedding(input=",".join(self.tags))

    def get_summary(self):
        hippocampus = HippocampusMgr().get_hippocampus(self.AID)
        for id, name in self.participant_ids.items():
            mem_entity = hippocampus.load_memory_of_user(id)
            if mem_entity is None or mem_entity.user_nickname == '':
                continue
            self.participant_ids[id] = mem_entity.user_nickname

        return self.summary.format(**self.participant_ids)

    def load_from_mongo(self):
        raise NotImplementedError

    def merge_event_block(self, *blocks):
        event_list = []
        for block in blocks:
            event_list.extend(block.origin_event)
        self.build_from_dialogue_event(event_list)

    def _zip_event_log(self) -> str:
        zipped_str = ""
        for event in self.origin_event:
            zipped_str += event.description() + "\n"
        return zipped_str

    def _build_name(self) -> str:
        return f"memory_block_{self.AID}_{self.create_timestamp}"

    # def maintain_similarity(self, id: str, sim: float):
    #     """
    #     Maintain top3 similar block
    #     :param id:
    #     :param sim: float (0, 1)
    #     :return:
    #     """
    #     while len(self.top3_similar_block) > 3:
    #         self.top3_similar_block.pop()
    #     for i in range(len(self.top3_similar_block)):
    #         if sim > self.top3_similar_block[i][1]:
    #             if len(self.top3_similar_block) >= 3:
    #                 self.top3_similar_block.pop(2)
    #             self.top3_similar_block.insert(i, (id, sim))
    #             return
    #     if len(self.top3_similar_block) < 3:
    #         self.top3_similar_block.append((id, sim))

# if __name__ == '__main__':
#     block = EventBlock(top3_similar_block=[("3", 0.3), ("2", 0.2)])
#     block.maintain_similarity("1", 0.1)
#     assert block.top3_similar_block == [("3", 0.3), ("2", 0.2), ("1", 0.1)]
#
#     block.maintain_similarity("4", 0.4)
#     assert block.top3_similar_block == [("4", 0.4), ("3", 0.3), ("2", 0.2)]
#
#     block.maintain_similarity("1", 0.1)
#     assert block.top3_similar_block == [("4", 0.4), ("3", 0.3), ("2", 0.2)]
#
#     block.maintain_similarity("5", 0.5)
#     assert block.top3_similar_block == [("5", 0.5), ("4", 0.4), ("3", 0.3)]
#
#     block.maintain_similarity("6", 0.45)
#     assert block.top3_similar_block == [("5", 0.5), ("6", 0.45), ("4", 0.4)]
#
#     block.top3_similar_block.append(("7", 0.6))
#     block.maintain_similarity("8", 0.55)
#     assert block.top3_similar_block == [("8", 0.55), ("5", 0.5), ("6", 0.45)]
#

# if __name__ == '__main__':
#     print(json.loads("""{
#     "summary": "Allen and Tina had a conversation about Allen feeling unhappy due to getting rejected by someone. Tina provided support and encouragement to Allen. They also discussed self-doubt and failure in an interview. Tina reassured Allen and encouraged him to keep trying.",
#     "occur_time": "in 2023-07-07 15:37:37",
#     "participants": ["Allen", "Tina"],
#     "tags": ["feeling unhappy", "rejection", "self-doubt", "failure in interview", "support", "encouragement", "keep trying"]
# }"""))
