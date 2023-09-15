from typing import List, Dict

from common_py.ai_toolkit.openAI import Message, ChatGPTClient
from common_py.client.azure_mongo import MongoDBClient

from memory_sdk import const


class ReflectionExtractor:

    def extract_reflection(self, additional_id_blocks: List[str]):
        res_list = self.mongo_client.find_from_collection(collection_name="AI_memory_block", filter={"_id": {"$in": additional_id_blocks}})
        summary_text = '\n'.join([item.get("summary") for item in res_list])
        participants: Dict[str, str] = {}
        for item in res_list:
            participants.update(item.get("participant_ids", {}))
        for uid, name in participants.items():
            openai_resp = self.openai_client.generate([
                Message(role="system", content=const.reflection_question),
                Message(role="user", content=summary_text)
            ])
            content = openai_resp.get_chat_content()


    def __init__(self, AID: str):
        self.AID = AID
        self.mongo_client: MongoDBClient = MongoDBClient()
        self.openai_client: ChatGPTClient = ChatGPTClient(temperature=0)