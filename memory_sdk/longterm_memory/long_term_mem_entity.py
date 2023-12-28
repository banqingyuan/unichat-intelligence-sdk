import json
import logging
import uuid
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional
from common_py.ai_toolkit.openAI import ChatGPTClient, Message
from common_py.client.chroma import ChromaCollection, VectorRecordItem
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from memory_sdk import const
from memory_sdk.const import gen_question_answer
from memory_sdk.instance_memory_block.event_block import EventBlock, load_event_block_by_name

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class LongTermMemoryEntity:

    def __init__(self, AID: str, target_id: str, chroma_collection: ChromaCollection = None):
        self.AID = AID
        self.target_id = target_id
        self.collection: Optional[ChromaCollection] = chroma_collection
        self.LLMClient = ChatGPTClient()
        self.ready: bool = False

    def set_collection(self, collection: ChromaCollection):
        self.collection = collection

    def set_ready(self):
        self.ready = True

    def upload_new_mem_block(self, mem_block_lst: List[EventBlock]):
        record_lst = []
        question_tasks = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            for mem_block in mem_block_lst:
                meta_data = {
                    "AID": self.AID,
                    "target_id": self.target_id,
                    "create_time": mem_block.create_timestamp,
                    "block_name": mem_block.name
                }
                task = executor.submit(self._gen_vector_index_from_mem_block, mem_block)
                question_tasks.append((meta_data, task))
        for tup in question_tasks:
            meta_data, task = tup
            questions = task.result()
            for question in questions:
                record_lst.append(VectorRecordItem(
                    id=str(uuid.uuid4()),
                    meta=meta_data,
                    documents=question
                ))
            record_lst.append(
                VectorRecordItem(
                    id=str(uuid.uuid4()),
                    meta=meta_data,
                    document=mem_block.raw_summary
                )
            )
        self.collection.upsert_many(record_lst)

    def _gen_vector_index_from_mem_block(self, mem_block: EventBlock) -> List[str]:
        chat_summary = mem_block.raw_summary
        question_num = 1
        if len(chat_summary) > 250:
            question_num = 2
        if len(chat_summary) > 500:
            question_num = 3
        question_index = []
        for i in range(3):
            try:
                gen_question_prompt = gen_question_answer.format(question_number=question_num,
                                                                 chat_summary=chat_summary)
                resp = self.LLMClient.generate(messages=[
                    Message(role='system', content=gen_question_prompt)
                ])
                if resp:
                    json_resp = json.loads(resp.get_chat_content())
                    if 'questions' not in json_resp or not isinstance(json_resp['questions'], list):
                        raise Exception(f"llm response expect questions key in json but not found: {json_resp}")
                    question_index.extend(json_resp['questions'])
                    break
            except Exception as e:
                logger.warning(f"gen vector index from mem block error: {e}")
                continue
        return question_index

    def _get_block_name_by_time_range(self, start_time: int, end_time: int, content: str = None, count: int = 2) -> List[str]:
        if not self.ready:
            logger.warning(f"LongTermMemoryEntity not ready, return empty list")
            return []
        if not content:
            query_res = self.collection.get(where={
                "$and": [
                    {"create_time": {"$gte": start_time}},
                    {"create_time": {"$lte": end_time}},
                ]
            }, limit=count*4)
            self._get_unique_block_name(query_res, count)
        else:
            query_res = self.collection.query(input_data=content, meta_filter={
                "$and": [
                    {"create_time": {"$gte": start_time}},
                    {"create_time": {"$lte": end_time}},
                ]
            }, top_k=count*4, threshold=0.7)
            return self._get_unique_block_name(query_res, count)

    def time_relevant_query(self, content: str, count: int = 3) -> List[str]:
        try:
            if not self.ready:
                logger.warning(f"LongTermMemoryEntity not ready, return empty list")
                return []
            time_range_tuple = self._generate_time_range(content)
            if not time_range_tuple:
                return []
            query_res = self.collection.query(input_data=content, meta_filter={
                "$and": [
                    {"create_time": {"$gte": time_range_tuple[0]}},
                    {"create_time": {"$lte": time_range_tuple[1]}},
                ]
            }, top_k=count*4, threshold=0.7)
            return self._get_unique_block_name(query_res, count)
        except Exception as e:
            logger.exception(e)
            return []

    def _generate_time_range(self, content: str) -> (int, int):
        # 获取当前时间
        current_time = datetime.now()

        # 格式化时间
        # 例如：%Y-%m-%d
        formatted_time = current_time.strftime("%Y-%m-%d")

        llm_res = self.LLMClient.generate(messages=[
            Message(role='system', content=const.get_target_timestamp.format(current_time=formatted_time,user_input=content))
        ])
        if not llm_res:
            logger.warning(f"llm response is None")
            return None
        try:
            llm_res_json = json.loads(llm_res.get_chat_content())
            if 'time_accuracy' not in llm_res_json or llm_res_json['time_accuracy'] not in ['day', 'month', 'year', 'week']:
                if llm_res_json['time_accuracy'] == 'undefined':
                    return None
                logger.warning(f"llm response json not found time_accuracy key or value error: {llm_res_json}")
                return None
            time_accuracy = llm_res_json['time_accuracy']
            target_formatted_time = llm_res_json['formatted_time']
            return self._get_timestamp_range_by_time_accuracy(time_accuracy, target_formatted_time)
        except Exception as e:
            logger.warning(f"llm response json parse error: {e}, origin response: {llm_res.get_chat_content()}")
            return None

    def _get_timestamp_range_by_time_accuracy(self, time_accuracy: str, target_formatted_time: str) -> (int, int):
        if time_accuracy == 'day':
            start_time = datetime.strptime(target_formatted_time, "%Y-%m-%d").timestamp()
            end_time = start_time + 24 * 3600
        elif time_accuracy == 'week':
            specified_date = datetime.strptime(target_formatted_time, "%Y-%m-%d")
            # 计算周一的日期
            # weekday() 方法返回的是周一为0，周日为6
            monday_delta = timedelta(days=specified_date.weekday())
            start_time = specified_date - monday_delta
            start_time = start_time.timestamp()
            end_time = start_time + 7 * 24 * 3600
        elif time_accuracy == 'month':
            start_time = datetime.strptime(target_formatted_time, "%Y-%m").timestamp()
            end_time = start_time + 31 * 24 * 3600
        elif time_accuracy == 'year':
            start_time = datetime.strptime(target_formatted_time, "%Y").timestamp()
            end_time = start_time + 365 * 24 * 3600
        else:
            raise Exception(f"time accuracy error: {time_accuracy}")
        return int(start_time), int(end_time)

    def get_block_name_by_text_input(self, content: str, count: int = 3) -> List[str]:
        try:
            if not self.ready:
                logger.warning(f"LongTermMemoryEntity not ready, return empty list")
                return []
            # 每个 summary 会生成四条query_index, count * 4是为了限制返回的最大数量。同时为了保证结果的多样性，不能让 top_k == count
            query_res = self.collection.query(input_data=content, meta_filter={}, top_k=count*4, threshold=0.7)
            return self._get_unique_block_name(query_res, count)
        except Exception as e:
            logger.exception(e)
            return []

    def _get_unique_block_name(self, query_res: List[VectorRecordItem], count: int) -> List[str]:
        block_name_dict = {}
        for res in query_res:
            block_name = res.meta.get('block_name', None)
            if not block_name:
                logger.error(f"block name not found in meta: {res.json()}")
                continue
            block_name_dict[block_name] = res.score

        # get top count block name
        if len(block_name_dict) <= count:
            block_name_lst = list(block_name_dict.keys())
        else:
            block_name_lst = sorted(block_name_dict, key=lambda x: block_name_dict[x], reverse=True)[:count]

        return block_name_lst

#
# if __name__ == '__main__':
#     target_formatted_time = '2022-06-27'
#     specified_date = datetime.strptime(target_formatted_time, "%Y-%m-%d")
#     # 计算周一的日期
#     # weekday() 方法返回的是周一为0，周日为6
#     monday_delta = timedelta(days=specified_date.weekday())
#     start_time = specified_date - monday_delta
#     start_time = start_time.timestamp()
#     end_time = start_time + 7 * 24 * 3600
#     print(start_time, end_time)

