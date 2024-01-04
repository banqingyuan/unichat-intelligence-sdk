import csv
import time
from datetime import datetime
from typing import List, Dict

from common_py.client.azure_mongo import MongoDBClient
from common_py.model.chat import ConversationEvent
from pydantic import BaseModel

from memory_sdk.instance_memory_block.event_block import EventBlock, from_mongo_res_to_event_block


class QueryOption(BaseModel):
    start_time: int = None
    end_time: int = None
    UIDs: List[str] = None
    AIDs: List[str] = None
    chat_content: str = None
    min_conversation_round_number: int = None
    max_conversation_round_number: int = None

    def set_time_range(self, start_time: str = None, end_time: str = None):
        # trans formatted time to timestamp
        if start_time:
            self.start_time = int(datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S').timestamp())
        if end_time:
            self.end_time = int(datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S').timestamp())
        return self

    def with_UIDs(self, *UIDs: str):
        self.UIDs = list(UIDs)
        return self

    def with_AIDs(self, *AIDs: str):
        self.AIDs = list(AIDs)
        return self

    def contain(self, chat_content: str):
        self.chat_content = chat_content
        return self

    def with_min_round_number(self, min_round_number: int):
        self.min_conversation_round_number = min_round_number
        return self

    def with_max_round_number(self, max_round_number: int):
        self.max_conversation_round_number = max_round_number
        return self


def _generate_query_filter_by_query_option(query_option: QueryOption):
    query_filter: Dict = {}

    # 时间范围过滤
    if query_option.start_time and query_option.end_time:
        query_filter['create_timestamp'] = {'$gte': query_option.start_time, '$lte': query_option.end_time}
    elif query_option.start_time:
        query_filter['create_timestamp'] = {'$gte': query_option.start_time}
    elif query_option.end_time:
        query_filter['create_timestamp'] = {'$lte': query_option.end_time}

    # UID 过滤
    if query_option.UIDs:
        query_filter['origin_event'] = {
            '$elemMatch': {
                'role': 'user',
                'speaker': {'$in': query_option.UIDs}
            }
        }

    # AID 过滤
    if query_option.AIDs:
        query_filter['AID'] = {'$in': query_option.AIDs}

    # 聊天内容过滤
    if query_option.chat_content:
        query_filter['origin_event.message'] = {'$regex': query_option.chat_content}

    # 对话轮次数过滤
    if query_option.min_conversation_round_number and query_option.max_conversation_round_number:
        query_filter['$expr'] = {
            '$and': [
                {'$gte': [{'$size': '$origin_event'}, query_option.min_conversation_round_number]},
                {'$lte': [{'$size': '$origin_event'}, query_option.max_conversation_round_number]}
            ]
        }
    elif query_option.min_conversation_round_number:
        query_filter['$expr'] = {'$gte': [{'$size': '$origin_event'}, query_option.min_conversation_round_number]}
    elif query_option.max_conversation_round_number:
        query_filter['$expr'] = {'$lte': [{'$size': '$origin_event'}, query_option.max_conversation_round_number]}

    return query_filter


def _save_to_csv(file_name: str, block_lst: list):
    # AI_dict: Dict = {}
    # for block in block_lst:
    #     if block.AID not in AI_dict:
    #         AI_dict[block.AID] = []
    #     AI_dict[block.AID].append(block)
    # for AID, block_lst in AI_dict.items():
    #     AI_dict[AID] = sorted(block_lst, key=lambda x: x.create_timestamp, reverse=True)
    block_lst = sorted(block_lst, key=lambda x: x.create_timestamp)

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
        for block in block_lst:
            AID = ''
            for event in block.origin_event:
                if isinstance(event, ConversationEvent):
                    if event.role == 'AI' and AID == '':
                        AID = event.speaker
                    formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(event.occur_time)))
                    writer.writerow([AID, f"{event.role}: {event.speaker_name}", event.message, formatted_time])
            writer.writerow(['', '', ''])


def query_conversation_history(file_name: str, query_option: QueryOption, limit: int = None):
    mongo_filter = _generate_query_filter_by_query_option(query_option)

    mongodb_client = MongoDBClient(DB_NAME='unichat-backend')
    block_lst: List[EventBlock] = []
    res = mongodb_client.find_from_collection('AI_memory_block', filter=mongo_filter, limit=limit)
    for item in res:
        block_lst.append(from_mongo_res_to_event_block(item))
    # sort by create_timestamp
    _save_to_csv(file_name, block_lst)


if __name__ == '__main__':
    query_option = QueryOption().set_time_range(start_time='2020-09-01 00:00:00', end_time='2024-12-30 23:59:59').contain('甘木').with_UIDs('22202679', '22202678')
    query_conversation_history('test', query_option, 10)
