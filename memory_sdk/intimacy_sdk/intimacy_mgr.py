import logging
import time
from typing import Dict, List
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.redis_client import RedisClient, RedisAIMemoryInfo
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from memory_sdk.intimacy_sdk.intimacy_ticket import IntimacyBase, IntimacyTicketChatTime
from memory_sdk.memory_entity import AI_memory_intimacy_level, AI_memory_intimacy_point

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class IntimacyMgr:
    """
    亲密度管理
    """
    intimacy_level2point = {
        1:    0,
        2:    100,
        3:    500,
        4:    1300,
    }

    support_level = {
        'just_met': 1,
        'casual_friend': 2,
        'special_friend': 3,
        'best_friend': 4,
        'romantic_relationship': 4,
    }

    def __init__(self):
        self.redis_client = RedisClient()
        self.mongo_db = MongoDBClient()
        self.intimacy_stash: Dict[str, List[IntimacyBase]] = {}
        self.uuid_map: Dict[str, List[IntimacyTicketChatTime]] = {}  # 有些亲密度单据需要合并，比如聊天时长，需要根据UUID进行合并

    def add_chat_time_intimacy(self, intimacy_ticket: IntimacyTicketChatTime):
        if intimacy_ticket.UUID not in self.uuid_map:  # 两个AI互相对话的时候这个逻辑会有一些问题，短期没有AI对话的需求，先不考虑
            self.uuid_map[intimacy_ticket.UUID] = [intimacy_ticket]
        else:
            self.uuid_map[intimacy_ticket.UUID].append(intimacy_ticket)

    def _add_in_stash(self, intimacy_ticket: IntimacyBase):
        intimacy_key = _assemble_key(intimacy_ticket)
        if intimacy_key not in self.intimacy_stash:
            self.intimacy_stash[intimacy_key] = [intimacy_ticket]
        else:
            self.intimacy_stash[intimacy_key].append(intimacy_ticket)

    def save_loop(self):
        while True:
            try:
                time.sleep(30)
                self._combine_chat_time_ticket()
                self._on_save()
            except Exception as e:
                logging.exception(e)
                continue

    def _combine_chat_time_ticket(self):
        # 合并聊天时长的单据
        for uuid, ticket_list in self.uuid_map:
            if len(ticket_list) == 0:
                continue
            current_ts = int(time.time())
            if not all([(current_ts - ticket.ts) > 30 for ticket in ticket_list]):
                # 半分钟内有更新，不进行保存
                continue
            if_user_in_chat = any([ticket.speaker != 'AI' for ticket in ticket_list])
            if_AI_in_chat = any([ticket.speaker == 'AI' for ticket in ticket_list])

            source_id = ticket_list[0].source_id
            target_id = ticket_list[0].target_id
            intimacy_from = ticket_list[0].intimacy_from
            # 保存
            if if_user_in_chat:
                add_value = 0
                ts = 0
                time_length = 0
                speaker = ''
                for ticket in ticket_list:
                    if ticket.speaker != 'AI':
                        add_value += ticket.add_value
                        ts = max(ts, ticket.ts)
                        time_length += ticket.chat_time_length
                        speaker = ticket.speaker
                user_intimacy_ticket = IntimacyTicketChatTime(source_id=source_id,
                                                              target_id=target_id,
                                                              intimacy_from=intimacy_from,
                                                              add_value=add_value,
                                                              chat_time_length=time_length,
                                                              ts=ts,
                                                              speaker=speaker,
                                                              UUID=uuid)
                self._add_in_stash(user_intimacy_ticket)
            if if_AI_in_chat:
                add_value = 0
                ts = 0
                time_length = 0
                speaker = ''
                for ticket in ticket_list:
                    if ticket.speaker == 'AI':
                        add_value += ticket.add_value
                        ts = max(ts, ticket.ts)
                        time_length += ticket.chat_time_length
                        speaker = ticket.speaker
                AI_intimacy_ticket = IntimacyTicketChatTime(source_id=source_id,
                                                            target_id=target_id,
                                                            intimacy_from=intimacy_from,
                                                            add_value=add_value,
                                                            chat_time_length=time_length,
                                                            ts=ts,
                                                            speaker=speaker,
                                                            UUID=uuid)
                self._add_in_stash(AI_intimacy_ticket)

    def _on_save(self):
        for intimacy_key, intimacy_ticket_list in self.intimacy_stash:
            source_id = intimacy_ticket_list[0].source_id
            target_id = intimacy_ticket_list[0].target_id
            add_value = sum([ticket.add_value for ticket in intimacy_ticket_list])

            intimacy_point_redis_key = RedisAIMemoryInfo.format(AID=source_id, UID=target_id)
            intimacy_point = self.redis_client.hget(intimacy_point_redis_key, AI_memory_intimacy_point)
            intimacy_point = int(intimacy_point) if intimacy_point else 0
            intimacy_point += add_value
            self.redis_client.hset(intimacy_point_redis_key, AI_memory_intimacy_point, intimacy_point)

            ids = self.mongo_db.create_document('AI_intimacy_record', [ticket.dict() for ticket in intimacy_ticket_list])
            logger.debug(f'create AI_intimacy_record ids: {[str(id) for id in ids]}')

    def _upgrade_intimacy_level(self, source_id: str, target_id: str, request_level: str) -> bool:
        if request_level not in self.support_level:
            raise ValueError(f'unsupported intimacy level: {request_level}')
        intimacy_point_redis_key = RedisAIMemoryInfo.format(AID=source_id, UID=target_id)
        intimacy_point = self.redis_client.hget(intimacy_point_redis_key, AI_memory_intimacy_point)
        intimacy_point = int(intimacy_point) if intimacy_point else 0
        level_request_point = self.intimacy_level2point[self.support_level[request_level]]
        if intimacy_point < level_request_point:
            return False
        self.redis_client.hset(intimacy_point_redis_key, AI_memory_intimacy_level, request_level)




def _assemble_key(intimacy_ticket: IntimacyBase) -> str:
    return f'{intimacy_ticket.source_id} intimacy towards {intimacy_ticket.target_id}'


if __name__ == '__main__':
    print(max([]))
