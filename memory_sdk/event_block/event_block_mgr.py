from typing import List, Dict
import logging
from common_py.ai_toolkit.openAI import Message, ChatGPTClient
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.redis_client import RedisClient
from common_py.model.base import BaseEvent

from memory_sdk import const
from memory_sdk.event_block.event_item import EventBlock
from common_py.utils.similarity import similarity

from memory_sdk.event_block.reflection_extractor import ReflectionExtractor
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from memory_sdk.memory_entity import UserMemoryEntity

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class BlockManager:
    """
    Each surviving AI instance will have an EventManager for managing memory modules,
    creating, merging, active storage and automatic storage if OnDestory
    """
    def create(self, event_slice: List[BaseEvent]):
        block = EventBlock(AID=self.AID)
        try:
            block.build_from_dialogue_event(event_slice)

            # _maintain_similarity may return origin block or merged block with high similarity
            # if merged block, delete origin block and add merged block
            new_block = self._maintain_similarity(block)
            new_block.importance = self._dialogue_importance(new_block)
            logger.debug(f"maintain similarity success")
            self.block_dict[block.name] = new_block
            self.save_later.append(new_block)
            if len(self.save_later) > 10:
                self._save_block()
        except Exception as e:
            logger.error(f"create error: {e}")
            return

    def on_destroy(self, memory_entities: Dict[str, UserMemoryEntity]):
        self._save_block(memory_entities)

    def _dialogue_importance(self, event_block: EventBlock) -> int:
        messages = [
            Message(role="system", content=const.dialogue_importance),
            Message(role="user", content=event_block.summary),
        ]
        for i in range(3):
            try:
                res = ChatGPTClient(temperature=0.0).generate(messages=messages)
                rate = self._parse_rate(res.get_chat_content())
                if rate is not None:
                    return rate
            except Exception as e:
                logger.error(f"dialogue importance error: {e}")
        return 3 # default importance

    def _parse_rate(self, res: str) -> int:
        """
        response might be: "rate: 3" or "3"
        :param res:
        :return:
        """
        res_str = res.strip()
        if res_str.isdigit():
            return int(res_str)
        # cut string before "Rating"
        if "Rating" in res_str:
            res_str = res_str[res_str.find("Rating"):]
        split_res = res_str.split(':')
        if len(split_res) == 2 and split_res[1].strip().isdigit():
            return int(split_res[1].strip())

    def _maintain_similarity(self, new_block: EventBlock) -> EventBlock:
        need_merge_event = []
        for block in self.save_later:
            sim = similarity(new_block.embedding_1536D, block.embedding_1536D)
            if sim > 0.9:
                logger.debug(f"similarity: {sim}, merge block: {block.name}, "
                             f"with content old: {block.summary}, new: {new_block.summary}")
                need_merge_event.append(block)
        if len(need_merge_event) > 0:
            need_merge_event.append(new_block)
            merged_block = EventBlock()
            merged_block.merge_event_block(*need_merge_event)
            for block in need_merge_event:
                if block.name in self.block_dict:
                    del self.block_dict[block.name]
                if block in self.save_later:
                    self.save_later.remove(block)
            return self._maintain_similarity(merged_block)
        return new_block

    def _save_block(self, memory_entities: Dict[str, UserMemoryEntity] = None):
        documents = []
        for event_block in self.save_later:
            if event_block.importance <= 3:
                continue
            documents.append(event_block.dict(exclude={'embedding_1536D', 'tags_embedding_1536D'}))
        if len(documents) == 0:
            logger.error(f"mongo db create error cause by empty documents")
            return
        self.mongo_client.create_document("AI_memory_block", documents, *['UID', 'AID'])
        logger.debug(f"mongo db create success, {documents}")

        # update user memory entity of good topic_mentioned_last_time
        for event_block in self.save_later:
            for uid in event_block.participant_ids:
                most_importance_of_user = self.uid_importance_mem_dict.get(uid, 0)
                if most_importance_of_user < event_block.importance:
                    self.uid_importance_mem_dict[uid] = event_block.importance
                    entity = memory_entities.get(uid, None)
                    if entity is not None:
                        entity.element_stash('topic_mentioned_last_time', event_block.summary)

        # redis_key = _gen_block_list_key(self.AID)
        # pipeline = self.redis_client.pipeline()
        # pipeline.lpush(redis_key, *mongo_ids)
        # pipeline.expire(redis_key, 60 * 60 * 24 * 7)
        # res = pipeline.execute()
        # list_length = int(res[0]) if len(res) > 0 and res[0].isdigit() else 0
        #
        # if list_length > 20:
        #     mem_block_ids = self.redis_client.lrange(redis_key, 0, -1)
        #     self.extract_reflection.extract_reflection(mem_block_ids)

        # 创建线程池提交pinecone任务
        # with ThreadPoolExecutor(max_workers=10) as executor:
        #     pinecone = PineconeClientFactory().get_client(index="knowledge-vdb", environment="us-west4-gcp-free")
        #     for i in range(len(documents)):
        #         upsert_request = {
        #                             'id': self.save_later[i].name,
        #                             'vector': self.save_later[i].tags_embedding_1536D,
        #                             'namespace': wrap_namespace(self.save_later[i].AID),
        #                             'metadata': {
        #                                 'participates': [],
        #                                 'memory_type': 'memory_block',
        #                                 'text_key': str(mongo_ids[i]),
        #                             }
        #                         }
        #         if len(self.save_later[i].participant_ids.keys()) > 0:
        #             upsert_request['metadata']['participates'] = list(self.save_later[i].participant_ids.keys())
        #         executor.submit(pinecone.upsert_index, **upsert_request)

        self.save_later.clear()

    def __init__(self, AID: str):
        self.save_later: List[EventBlock] = []
        self.block_dict: Dict[str, EventBlock] = {}
        self.mongo_client = MongoDBClient()
        self.AID = AID
        self.redis_client = RedisClient()
        self.uid_importance_mem_dict = {}

        self.extract_reflection = ReflectionExtractor(self.AID)


def _gen_block_list_key(AID: str) -> str:

    h = hash(AID)
    # 分片到0-23小时，分段处理
    partition = str(h % 24)
    return f"AI_memory_block_list_{partition}_{AID}"
