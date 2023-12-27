import csv
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional
from common_py.ai_toolkit.openAI import ChatGPTClient, Message
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.embedding import OpenAIEmbedding
from common_py.const.ai_attr import Entity_type_user
from common_py.model.base import BaseEvent
from common_py.model.chat import ConversationEvent
from common_py.model.scene.scene import SceneEvent
from common_py.model.system_hint import SystemHintEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from common_py.utils.util import get_random_str
from pydantic import BaseModel
from memory_sdk import const
from memory_sdk.memory_entity import UserMemoryEntity

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
    raw_summary: str = ""  # 未被替换成id的summary，可读性更好一些

    participant_ids: Dict[str, str] = {}
    participants: List[str] = []
    tags: List[str] = []
    create_timestamp: int = 0
    last_active_timestamp: int = 0
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
                chatting_speaker[event.speaker_name] = event.speaker
        replaced_summary = extract_content["summary"]
        if len(chatting_speaker) > 0 :
            speaker_name_to_id = ""
            example_username = list(chatting_speaker.keys())[0]
            example_UID = chatting_speaker[example_username]
            for name, id in chatting_speaker.items():
                # 因为数字无法作为格式化字符串的key，所以加上一个后缀
                speaker_name_to_id += f"username {name} with id: {id} \n"
            summary_response = ChatGPTClient(temperature=0).generate(messages=
            [
                Message(role="system", content=const.change_name_to_id.format(example_username=example_username, example_UID=example_UID) + speaker_name_to_id),
                Message(role="user", content=replaced_summary)
            ]
            )

            replaced_summary = summary_response.get_chat_content()

        self.tags = extract_content["tags"]
        self.participants = extract_content["participants"]
        self.summary = replaced_summary
        self.raw_summary = extract_content["summary"]
        logger.debug(f"summary result: {self.summary}")
        embedding = OpenAIEmbedding()
        self.embedding_1536D = embedding(input=self.summary)
        self.tags_embedding_1536D = embedding(input=",".join(self.tags))

    def get_summary(self):
        for id, name in self.participant_ids.items():
            try:
                mem_entity = UserMemoryEntity(self.AID, id, Entity_type_user)
                if mem_entity is None or mem_entity.target_nickname == '':
                    continue
                self.participant_ids[id] = mem_entity.target_nickname
            except Exception as e:
                logger.error(f"get_summary error: {e}")
                continue

        summary = self.summary
        for id, name in self.participant_ids.items():
            summary = summary.replace(f'{{{id}}}', name)
        return summary

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
        return f"memory_block_{self.AID}_{self.create_timestamp}_{get_random_str(10)}"


def load_block_from_mongo(block_name: str) -> EventBlock:
    mongo_client = MongoDBClient()
    res = mongo_client.find_one_from_collection('AI_memory_block', {'name': block_name})
    if not res:
        raise Exception(f"can not find block: {block_name}")
    del res['origin_event']
    block = EventBlock(**res)
    return block


def from_mongo_res_to_event_block(res: Dict) -> EventBlock:
    origin_event = res['origin_event']
    events = []
    for e in origin_event:
        if e.get('event_source', '') == 'conversation':
            events.append(ConversationEvent(**e))
        elif e.get('event_source', '') == 'system_hint':
            events.append(SystemHintEvent(**e))
        elif e.get('event_source', '') == 'scene_event':
            events.append(SceneEvent(**e))
    del res['origin_event']
    block_item = EventBlock(**res)
    block_item.origin_event = events
    return block_item


def load_event_block_by_name(block_name: str) -> Optional[EventBlock]:
    mongo_client = MongoDBClient()
    block_res = mongo_client.find_one_from_collection('AI_memory_block', {'name': block_name})
    if not block_res:
        logger.error(f"can not find block: {block_name}")
        return None
    del block_res['origin_event']
    block = EventBlock(**block_res)
    return block


def load_user_block_from_mongo(UID: str) -> List[EventBlock]:
    block_lst: List[EventBlock] = []
    mongo_client = MongoDBClient()
    res = mongo_client.find_from_collection('AI_memory_block', filter={f'participant_ids.{UID}': {'$exists': True}})
    for item in res:
        block_lst.append(from_mongo_res_to_event_block(item))
    return block_lst


def _save_to_csv(file_name: str, block_lst: dict):
    AI_dict: Dict = {}
    for block in block_lst:
        if block.AID not in AI_dict:
            AI_dict[block.AID] = []
        AI_dict[block.AID].append(block)
    for AID, block_lst in AI_dict.items():
        AI_dict[AID] = sorted(block_lst, key=lambda x: x.create_timestamp, reverse=True)

    # last_time_lst = []
    # for AID, block_lst in AI_dict.items():
    #     for block in block_lst:
    #         last_time = int(block.origin_event[-1].occur_time) - int(block.origin_event[0].occur_time)
    #         last_time_lst.append(last_time)
    # print(last_time_lst)

    # save as csv
    with open(f'{file_name}.csv', 'w', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['AID', 'role: speaker', 'message', 'occur time'])
        for AID, block_lst in AI_dict.items():
            for block in block_lst:
                for event in block.origin_event:
                    if isinstance(event, ConversationEvent):
                        if event.role == 'AI' and AID == '':
                            AID = event.speaker
                        formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(event.occur_time)))
                        writer.writerow([AID, f"{event.role}: {event.speaker_name}", event.message, formatted_time])
                writer.writerow(['', '', ''])


if __name__ == '__main__':
    mongodb_client = MongoDBClient(DB_NAME='unichat-backend')
    uid_lst = ['22202148','22200108','22202188','22200264','22201987','22200366','22200842','22201646','22200094','22202119','22200273','22201506','22201801','22200005','22202135','22200256','22201992','22201136','22202047','22200004','22200227','22200702','22200007','22200424','22202105','22201724','22200002','22200003','22201426','22201429','22201462','22200805','22201045','22201502','22201754','22201169','22202251','22201840','22202209','22200629','22202272','22200444','22200206','22200261','22201633','22201647','22200150','22201515','22201772','22200095','22200100','22201980','22200922','22200654','22201626','22200323','22201520','22201509','22201867','22201577','22200685','22201143','22200051','22201148','22201655','22200694','22201604','22201293','22200793','22200308','22201974','22200542','22200433','22201533','22200423','22201295','22200362','22201613','22200196','22200050']
    idx = 1
    task_lst = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for uid in uid_lst:
            task_lst.append(executor.submit(load_user_block_from_mongo, uid))

    for task in task_lst:
        res = task.result()
        _save_to_csv(f'./csv/{idx}', res)
        idx += 1

