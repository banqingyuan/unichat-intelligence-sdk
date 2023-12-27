import logging
import threading
import time
from copy import deepcopy
from typing import Dict, List
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.redis_client import RedisClient
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from memory_sdk.hippocampus import HippocampusMgr
from memory_sdk.intimacy_sdk.intimacy_ticket import IntimacyBase, IntimacyTicketChatTime
from memory_sdk.memory_entity import UserMemoryEntity

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

JUST_MET = 'just_met'
CASUAL_FRIEND = 'casual_friend'
SPECIAL_FRIEND = 'special_friend'
BEST_FRIEND = 'best_friend'
ROMANTIC_PARTNER = 'romantic_partner'


class IntimacyMgr:
    """
    亲密度管理
    """
    _instance_lock = threading.Lock()

    intimacy_level2point = {
        1: 0,
        2: 40,
        3: 440,
        4: 1240,
    }

    support_level = {
        JUST_MET: 1,
        CASUAL_FRIEND: 2,
        SPECIAL_FRIEND: 3,
        BEST_FRIEND: 4,
        ROMANTIC_PARTNER: 4,
    }

    def __init__(self, need_init: bool = False):
        if need_init:
            self.redis_client = RedisClient()
            self.mongo_db = MongoDBClient()
            self.intimacy_stash: Dict[str, List[IntimacyBase]] = {}
            self.uuid_map: Dict[str, List[IntimacyTicketChatTime]] = {}  # 有些亲密度单据需要合并，比如聊天时长，需要根据UUID进行合并

    def add_chat_time_intimacy(self, intimacy_ticket: IntimacyTicketChatTime):
        if intimacy_ticket.UUID not in self.uuid_map:  # 两个AI互相对话的时候这个逻辑会有一些问题，短期没有AI对话的需求，先不考虑
            self.uuid_map[intimacy_ticket.UUID] = [intimacy_ticket]
        else:
            self.uuid_map[intimacy_ticket.UUID].append(intimacy_ticket)

    def get_intimacy_level(self, UID: str, AID: str) -> str:
        """
        获取亲密度等级
        :param UID: 用户ID
        :param AID: AI ID
        :return: 亲密度等级
        """
        try:
            entity = HippocampusMgr().get_hippocampus(AID).load_memory_of_user(UID)
            if not entity:
                return JUST_MET
            intimacy_level = entity.get_intimacy_level()
            return intimacy_level
        except Exception as e:
            logger.error(f'get intimacy level error: {e}')
            return JUST_MET

    def get_intimacy_point(self, UID: str, AID: str) -> int:
        """
        获取亲密度点数
        :param UID: 用户ID
        :param AID: AI ID
        :return: 亲密度点数
        """
        try:
            entity = HippocampusMgr().get_hippocampus(AID).load_memory_of_user(UID)
            if not entity:
                return 0
            intimacy_point = entity.get_intimacy_point()
            return intimacy_point
        except Exception as e:
            logger.error(f'get intimacy point error: {e}')
            return 0

    def get_intimacy_info(self, UID: str, AID: str) -> (int, str, int, int):
        try:
            entity = HippocampusMgr().get_hippocampus(AID).load_memory_of_user(UID, True)
            if not entity:
                return 0, JUST_MET, 0, 0
            intimacy_point = entity.get_intimacy_point()
            intimacy_level = entity.get_intimacy_level()
            level = self.support_level[intimacy_level]
            if level == 4:
                intimacy_needed_to_next_level = 2000
            else:
                intimacy_needed_to_next_level = self.intimacy_level2point[level + 1] - self.intimacy_level2point[level]
            intimacy_got_this_level = intimacy_point - self.intimacy_level2point[level]

            if intimacy_got_this_level > intimacy_needed_to_next_level:
                intimacy_got_this_level = intimacy_needed_to_next_level

            if intimacy_got_this_level < 0:
                intimacy_got_this_level = 0

            return intimacy_point, intimacy_level, intimacy_needed_to_next_level, intimacy_got_this_level
        except Exception as e:
            logger.error(f'get intimacy info error: {e}')
            return 0, JUST_MET, 0, 0

    def set_ideal_intimacy(self, UID: str, AID: str, ideal_intimacy: str):
        mem_entity = HippocampusMgr().get_hippocampus(AID).load_memory_of_user(UID, True)
        if ideal_intimacy not in [BEST_FRIEND, ROMANTIC_PARTNER]:
            raise ValueError(f'unsupported ideal intimacy: {ideal_intimacy}')
        mem_entity.set_ideal_level(ideal_intimacy)
        self._check_and_update_intimacy(UID, AID, False)


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

    # def intimacy_display(self, UID: str, AID: str) -> Dict[str, int]:
    #     """
    #     亲密度展示
    #     :return: 亲密度展示
    #     """
    #     try:
    #         intimacy_display = {}
    #         for key, value in self.redis_client.redis_intimacy_display.items():
    #             intimacy_display[key] = value
    #         return intimacy_display
    #     except Exception as e:
    #         logger.error(f'intimacy display error: {e}')
    #         return {}

    def _combine_chat_time_ticket(self):
        combined_uuid_lst = []
        # 合并聊天时长的单据
        for uuid, ticket_list in self.uuid_map.items():
            if len(ticket_list) == 0:
                continue
            current_ts = int(time.time())
            if not all([(current_ts - ticket.ts) > 30 for ticket in ticket_list]):
                # 半分钟内有更新，不进行保存
                continue
            combined_uuid_lst.append(uuid)
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
        for uuid in combined_uuid_lst:
            del self.uuid_map[uuid]

    def _on_save(self):
        new_dict = deepcopy(self.intimacy_stash)
        self.intimacy_stash = {}
        for intimacy_key, intimacy_ticket_list in new_dict.items():
            source_id = intimacy_ticket_list[0].source_id
            target_id = intimacy_ticket_list[0].target_id
            add_value = sum([ticket.add_value for ticket in intimacy_ticket_list])

            # 这里也只处理了AI对人的亲密度，对target_id是uid做了假设
            mem_entity = HippocampusMgr().get_hippocampus(source_id).load_memory_of_user(target_id)
            if mem_entity is None:
                # 防止exception，日志里面打过了
                continue
            current_intimacy_point = mem_entity.add_intimacy_point(add_value)

            ids = self.mongo_db.create_document(
                'AI_intimacy_record',
                [ticket.dict() for ticket in intimacy_ticket_list],
                *['source_id', 'target_id']
            )

            self._check_and_update_intimacy(source_id, target_id, False)

            logger.debug(f'create AI_intimacy_record ids: {[str(id) for id in ids]} current intimacy point: {current_intimacy_point}')

    def _check_and_update_intimacy(self, source_id: str, target_id: str, need_upgrade: bool):
        mem_entity = HippocampusMgr().get_hippocampus(source_id).load_memory_of_user(target_id, need_upgrade)
        need_upgrade, new_intimacy_level = self._time_to_upgrade_intimacy(mem_entity)
        if need_upgrade:
            self._upgrade_intimacy_level(new_intimacy_level, mem_entity)

    def _time_to_upgrade_intimacy(self, mem_entity: UserMemoryEntity) -> (bool, False):

        tmp_relation_mapping = {
            1: JUST_MET,
            2: CASUAL_FRIEND,
            3: SPECIAL_FRIEND,
        }

        current_intimacy_point = mem_entity.get_intimacy_point()
        current_level_str = mem_entity.get_intimacy_level()
        new_expected_level_int = 1

        for level_int, point in reversed(self.intimacy_level2point.items()):
            if current_intimacy_point > point:
                new_expected_level_int = level_int
                break
        # todo 不是所有的AI都有浪漫关系亲密度选项
        if new_expected_level_int < 4:
            new_expected_level_str = tmp_relation_mapping[new_expected_level_int]
            if new_expected_level_str != current_level_str:
                return True, new_expected_level_str
        elif new_expected_level_int == 4:
            ideal_level = mem_entity.get_ideal_level()
            if not ideal_level or ideal_level not in [BEST_FRIEND, ROMANTIC_PARTNER]:
                return False, ''
            if ideal_level != current_level_str:
                return True, ideal_level

        return False, ''

    def _upgrade_intimacy_level(self, request_level: str, mem_entity: UserMemoryEntity) -> bool:
        if request_level not in self.support_level:
            raise ValueError(f'unsupported intimacy level: {request_level}')

        intimacy_point = mem_entity.get_intimacy_point()
        level_request_point = self.intimacy_level2point[self.support_level[request_level]]
        if intimacy_point < level_request_point:
            return False
        mem_entity.set_intimacy_level(request_level)
        logger.info(f'upgrade intimacy level to {request_level} for {mem_entity.AID} {mem_entity.target_id}')

    def __new__(cls, *args, **kwargs):
        if not hasattr(IntimacyMgr, "_instance"):
            with IntimacyMgr._instance_lock:
                if not hasattr(IntimacyMgr, "_instance"):
                    IntimacyMgr._instance = object.__new__(cls)
        return IntimacyMgr._instance


def _assemble_key(intimacy_ticket: IntimacyBase) -> str:
    return f'{intimacy_ticket.source_id} intimacy towards {intimacy_ticket.target_id}'

if __name__ == '__main__':
    mp = {
        1: 'a',
        2: 'b',
        3: 'c',
        4: "d",
    }
    for k, v in reversed(mp.items()):
        print(k, v)
