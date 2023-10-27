import json
import logging
import queue
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict
from common_py.ai_toolkit.openAI import filter_brackets

from common_py.client.azure_mongo import MongoDBClient
from common_py.client.pg import query_vector_info
from common_py.client.redis_client import RedisClient
from common_py.dto.ai_instance import AIBasicInformation, InstanceMgr
from common_py.dto.lui_usecase import LUIUsecaseInfo, LUIUsecase
from common_py.dto.unicaht_knowledge import UnichatKnowledge
from common_py.dto.user import UserInfoMgr
from opencensus.trace.tracer import Tracer

from memory_sdk.hippocampus import HippocampusMgr

specific_key = ['input', 'datasource']
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

condition_elements = ['left_variable', 'operator', 'right_value']


class PromptLoader:

    def parse_prompt(self, input_str: str, prompt_tpl: dict, tracer: Tracer, **kwargs) -> str:
        # with tracer.span(name="load_prompt_template_datasource"):
        #     variable_data = self._process_datasource(**params)
            # if "persona" in variable_data:
            #     variable_data.update(variable_data["persona"])
            #     variable_data.pop("persona")
        with tracer.span(name="assemble_prompt") as span:
            prompt_queue: queue.Queue = queue.Queue()

            with ThreadPoolExecutor(max_workers=5) as executor:
                idx = 0
                for tpl_name, tpl_block in prompt_tpl.items():
                    executor.submit(self._get_prompt_block, idx, tpl_block, input_str, prompt_queue, **kwargs)
                    idx += 1
            res_list = []
            while not prompt_queue.empty():
                res_list.append(prompt_queue.get())
            # 按照 idx 从小到大排序
            sorted_lst = sorted(res_list, key=lambda x: x[0])

            # 将排序后的字符串通过 \n 连接起来
            result = '\n'.join([item[1] for item in sorted_lst])
            return result

    def find_useful_LUI(self, inputs: List[str],
                        AI_info: AIBasicInformation,
                        speaker_id: str,
                        tracer: Tracer) -> Dict[str, bool]:
        with tracer.span(name="find_useful_LUI"):
            access_level = ['public']
            if AI_info.UID == speaker_id:
                access_level.append('private')
            q = queue.Queue()
            lui_results = {}
            with ThreadPoolExecutor(max_workers=5) as executor:
                for message_input in inputs:
                    message_input = filter_brackets(message_input)
                    result = re.split(r'[;.,?!]', message_input)
                    for item in result:
                        executor.submit(self._query_lui_library_from_pgvector, item, AI_info.type, access_level, q)
            while not q.empty():
                res = q.get()
                lui_results.update(res)
            logger.debug(f"recall lui results: {[key for key in lui_results.keys()]}")
            return lui_results

    def _query_lui_library_from_pgvector(self,
                                         input_str: str,
                                         AI_type: str,
                                         access_level: List[str],
                                         q: queue.Queue):
        try:
            lui_functions = {}
            results: List = query_vector_info(
                model=LUIUsecase,
                input_data=input_str,
                meta_filter={"$and": [
                    {"AI_type": {"$eq": AI_type}},
                    {"access_level": {"$in": access_level}}
                ]},
                top_k=3,
                threshold=0.9,
            )
            results = [LUIUsecaseInfo(**item) for item in results]
            for result in results:
                lui_functions[result.function_name] = True
            q.put_nowait(lui_functions)
        except Exception as e:
            logger.exception(e)

    def _get_prompt_block(self, idx: int, tpl: dict, chat_input: str, q: queue.Queue, **kwargs):
        # todo 注意一下chat_input为空的处理
        try:
            fixed_tpl = tpl.get("tpl", None)
            fixed_res = ""
            try:
                if fixed_tpl is not None:
                    variables_res = self._get_variables_results(tpl, chat_input, **kwargs)
                    condition = tpl.get('condition', None)
                    if condition is not None:
                        condition_res = self._get_condition_results(condition, **variables_res)
                        if condition_res:
                            fixed_res = fixed_tpl.format(**variables_res)
                        else:
                            return
                    fixed_res = fixed_tpl.format(**variables_res)
            except KeyError as e:
                logger.warning(f"variable not found when try to format tpl :{fixed_tpl}. key: {e}")
            q.put((idx, fixed_res))
            return
        except Exception as e:
            logger.exception(e)

    # def _get_reflection_results(self, reflection, chat_input, **params) -> str:
    #     # Calculating the similarity of two 1536-dimensional vectors takes on average 1ms
    #     accepted_reflection = {}
    #     chat_embedding = OpenAIEmbedding()(input=chat_input)
    #     top_3_of_description = []
    #     top_3_of_content = []
    #     for reflection_name, reflection_source in reflection.items():
    #         reflection_res = params.get(reflection_name, None)
    #         if reflection_res is None:
    #             if "vector_database" in reflection_source:
    #                 accepted_reflection[reflection_name] = self._get_vector_database(
    #                     reflection_source["vector_database"], chat_embedding, **params)
    #             continue
    #         reflection_description_embedding = reflection_res.get('description_embedding', None)
    #         reflection_content_embedding = reflection_res.get('content_embedding', None)
    #         reflection_value = reflection_res.get('value', None)
    #
    #         description_similarity = similarity(chat_embedding, reflection_description_embedding)
    #         content_similarity = similarity(chat_embedding, reflection_content_embedding)
    #
    #         self._maintain_top3(top_3_of_description, (description_similarity, reflection_name, reflection_value))
    #         self._maintain_top3(top_3_of_content, (content_similarity, reflection_name, reflection_value))
    #     for item in top_3_of_content:
    #         accepted_reflection[item[1]] = item[2]
    #     for item in top_3_of_description:
    #         accepted_reflection[item[1]] = item[2]
    #     reflection_str = '\n'.join([f'{value}' for value in accepted_reflection.values()])
    #     return reflection_str

    # def _get_vector_database(self, vdb_info, chat_embedding: List[float], **params) -> str:
    #     namespace = vdb_info.get('namespace', None)
    #     metadata = vdb_info.get('metadata', [])
    #     topK = vdb_info.get('top', 2)
    #     if namespace is None or metadata is None:
    #         return ""
    #     namespace = namespace.format(**params)
    #     query_dict = {}
    #     if len(metadata) > 1:
    #         query_list = []
    #         for meta_item in metadata:
    #             query_list.append(self._parse_single_metadata(meta_item, **params))
    #         query_dict['$and'] = query_list
    #     elif len(metadata) == 1:
    #         query_dict = self._parse_single_metadata(metadata[0], **params)
    #     logger.debug(f"query from vector database with namespace {namespace}, filter: {query_dict}")

        # index = vdb_info['index_name']
        # resp = PineconeClientFactory().get_client(index=index, environment="us-west4-gcp-free").query_index(
        #     namespace=namespace,
        #     vector=chat_embedding,
        #     top_k=topK,
        #     filter=query_dict,
        #     include_metadata=True
        # )
        # if 'matches' not in resp:
        #     return ""
        # vec_res = []
        # with ThreadPoolExecutor(max_workers=5) as executor:
        #     for match in resp['matches']:
        #         if 'metadata' not in match:
        #             continue
        #         metadata = match['metadata']
        #         if 'text_key' not in metadata:
        #             continue
        #         executor.submit(self._get_text_from_blob, vdb_info, metadata, vec_res)
        # logger.debug(f"vector database query result: {vec_res}")
        # return '\n'.join(vec_res)

    # def _get_text_from_blob(self, vdb_info, metadata, vec_res: list):
    #     text_key = metadata['text_key']
    #     text_store = vdb_info['text_store']
    #     data = ""
    #     if text_store['type'] == 'redis':
    #         data = self.redis_client.get(text_key)
    #     elif text_store['type'] == 'mongodb':
    #         res = self.mongodb_client.find_one_from_collection(text_store['collection'], {'_id': ObjectId(text_key)})
    #         if res is None:
    #             return
    #         data = res[text_store.get('field', 'text')]
    #     vec_res.append(data)

    # def _maintain_top3(self, top3_list: List, item: tuple):
    #     if len(top3_list) < 3:
    #         top3_list.append(item)
    #     else:
    #         min_index = min(enumerate(top3_list), key=lambda x: x[1][0])[0]
    #         if item[0] > top3_list[min_index][0]:
    #             top3_list[min_index] = item
    #     top3_list.sort(key=lambda x: x[0], reverse=True)
    #     return top3_list

    def _get_variables_results(self, tpl: dict, chat_input: str, **kwargs) -> dict:
        variables = tpl.get("variables", None)
        variable_res = {}
        if variables is not None:
            for key, variable in variables.items():
                # looking for redis cache, if not cached, then query from pg if pg source exists
                default_value = variable.get('default', None)
                if default_value is not None:
                    variable_res[key] = default_value
                if 'datasource' in variable and 'property' in variable:
                    try:
                        input_params = variable.get('input_params', {})
                        tmp_res = self._get_variable_from_datasource(variable['datasource'], variable['property'], input_params, **kwargs)
                        if tmp_res is not None:
                            variable_res[key] = tmp_res
                    except Exception as e:
                        logger.exception(e)
                        continue
                elif 'vector_database' in variable:
                    try:
                        vdb_info = variable['vector_database']
                        model = vdb_info['model']
                        meta_filter = vdb_info['meta_filter']
                        top_k = vdb_info.get('top_k', 2)
                        threshold = vdb_info.get('threshold', None)
                        content_field = vdb_info['content_field']
                        if model == 'UnichatKnowledge':
                            res = query_vector_info(UnichatKnowledge, chat_input, meta_filter, top_k, threshold=threshold)
                            if res is None or len(res) == 0:
                                continue
                        else:
                            logger.error(f"model {model} not supported")
                            continue
                        var_res = '\n'.join([item[content_field] for item in res])
                        variable_res[key] = var_res
                    except KeyError as e:
                        logger.exception(e)
                        continue

                # else:
                # if 'db_source' not in variable:
                #     raise Exception(f"variable {key} has no db_source and can not found in redis")
                # if 'pg_table' not in self.datasource:
                #     raise Exception(f"variable {key} has no pg_table and can not found in redis")
                # database_key = variable['db_source']
                # table, column_pair = database_key.split('#')[0], database_key.split('#')[1]
                # column_name, column_value = column_pair.split(':')[0], column_pair.split(':')[1]
                # if table in self.db_result:
                #     table_res = self.db_result[table]
                #     if column_name not in table_res:
                #         raise Exception(f"column {column_name} not found in table {table}")
                #     variable_res[key] = table_res[column_name]
                #     continue
                # with self._db_query_lock:
                #     if table not in self.db_result:
                #         with Session(self.pg_instance) as session:
                #             value = params.get(column_value, None)
                #             if value is None:
                #                 raise Exception(f"column {column_value} not found in params")
                #             result = session.execute(text(f"select * from {table} where {column_name} = {value}"))
                #             rows = result.fetchall()
                #             if len(rows) == 0:
                #                 raise Exception(f"column {column_name} not found in table {table}")
                #             logger.debug(
                #                 f"query table {table} with column {column_name} = {value}, res: {rows}, type: {type(rows)}")
                #             self.db_result[table] = rows[0]
                # if table in self.db_result:
                #     table_res = self.db_result[table]
                #     if column_name not in table_res:
                #         raise Exception(f"column {column_name} not found in table {table}")
                #     variable_res[key] = table_res[column_name]
                #     continue
                # else:
                #     raise Exception(f"column {column_name} not found either in table {table} or in redis")
        return variable_res

    # def _process_datasource(self, **params) -> dict:
    #     data_map = {}
    #     if 'input' not in params or 'datasource' not in params:
    #         raise Exception(f"input or datasource not found in params")
    #     required_params: List[str] = params.pop("input")
    #     for param in required_params:
    #         if param not in params:
    #             raise Exception(f"param {param} not found")
    #     datasource = params.pop("datasource", {})
    #
    #     data_map.update(params)
    #     logger.debug(f"process datasource with params {params.keys()}")
    #     if "redis" in datasource:
    #         for redis_detail in datasource["redis"]:
    #             redis_key_tpl = redis_detail.get("key_tpl", None)
    #             if not redis_key_tpl:
    #                 raise Exception(f"redis key not found in datasource {datasource}")
    #             redis_key = redis_key_tpl.format(**data_map)
    #             # hash_key = '_'.join([redis_key, "hash"])
    #             # hash_res = self.redis_client.get(hash_key)
    #             # if hash_res is None:
    #             #     logger.warning(f"redis_key {redis_key} has no hash key")
    #             # elif hash_key in self.redis_hash_dict and self.redis_hash_dict[hash_key] == hash_res:
    #             if redis_key in self.redis_data:
    #                 data_map.update(self.redis_data[redis_key])
    #                 continue
    #
    #             redis_data = {}
    #             if redis_detail.get('method', None) == "hmget":
    #                 if redis_detail["keymap"] is None:
    #                     raise Exception(f"keymap not found in redis detail {redis_detail}")
    #                 keymap = redis_detail["keymap"]
    #                 if type(keymap) is not dict:
    #                     raise Exception(f"keymap should be a dict")
    #                 redis_res = self.redis_client.hmget(redis_key, keymap.keys())
    #                 # decode
    #                 redis_res = [item.decode('utf-8') if item is not None else None for item in redis_res]
    #                 for key, value in zip(keymap.keys(), redis_res):
    #                     if value is None:
    #                         logger.warning(f"failed to load redis_key {redis_key} cause redis key not found")
    #                         continue
    #                     redis_data[keymap[key]] = value
    #             else:
    #                 raise Exception(f"redis method {redis_detail['method']} not supported")
    #             if redis_data is None:
    #                 logger.warning(f"failed to load redis_key {redis_key} cause redis key not found")
    #                 continue
    #             self.redis_data[redis_key] = redis_data
    #             # if hash_res is not None:
    #             #     self.redis_hash_dict[hash_key] = hash_res
    #             # else:
    #             #     # 如果从来没有设置过hash，说明写入方不支持，在这里帮忙hash一下
    #             #     hash_val = md5(json.dumps(redis_data).encode('utf-8')).hexdigest()
    #             #     self.redis_client.set(hash_key, hash_val)
    #             #     self.redis_hash_dict[hash_key] = hash_val
    #             data_map.update(redis_data)
    #     return data_map

    # def _parse_single_metadata(self, meta_item: str, **params):
    #     meta_elements = meta_item.split(':')
    #     if len(meta_elements) != 3:
    #         raise Exception(f"metadata {meta_item} has wrong format")
    #     meta_name, operator, meta_value_tpl = meta_elements[0], meta_elements[1], meta_elements[2]
    #     meta_value = meta_value_tpl.format(**params)
    #     query_dict = {}
    #     if operator == 'contain':
    #         value_list = meta_value.split(',')
    #         query_dict[meta_name] = {'$in': value_list}
    #     elif operator == 'equal':
    #         query_dict[meta_name] = meta_value
    #     else:
    #         raise Exception(f"vector database operator {operator} not support yet")
    #     return query_dict

    def _get_condition_results(self, condition, **param) -> bool:
        if not all([key in condition_elements for key in condition.keys()]):
            raise Exception(f"condition {condition} not satisfied")
        if condition['operator'] == 'eq':
            left_variable = condition['left_variable']
            if type(condition['left_variable']) == dict:
                left_variable = self._get_condition_results(condition['left_variable'], **param)
            left_value = param.get(left_variable, None)
            if left_value is None:
                logger.error(f"left_value {left_variable} not found in param {param}")
                return False
            right_value = condition['right_value']
            if hasattr(left_value, '__eq__') and hasattr(right_value, '__eq__'):
                return left_value == right_value
            else:
                raise Exception(f'left_variable {left_value} or right_value {right_value} has no operation eq')
        else:
            logger.error('prompt condition only support eq yet')
            return False
        # elif condition['operator'] == 'and':
        #     left_variable = condition['left_variable']
        #     if type(condition['left_variable']) == dict:
        #         left_variable = self._get_condition_results(condition['left_variable'], **param)
        #     left_value = param.get(left_variable, None)
        #     if left_value is None:
        #         raise Exception(f"left_value {left_variable} not found in param {param}")
        #     right_value = condition['right_value']
        #     if type(left_value) == bool and type(right_value) == bool:
        #         return left_value & right_value
        #     else:
        #         raise Exception(f'left_variable {left_value} or right_value {right_value} has no operation and')
        # elif condition['operator'] == 'or':
        #     left_variable = condition['left_variable']
        #     if type(condition['left_variable']) == dict:
        #         left_variable = self._get_condition_results(condition['left_variable'], **param)
        #     left_value = param.get(left_variable, None)
        #     if left_value is None:
        #         raise Exception(f"left_value {left_variable} not found in param {param}")
        #     right_value = condition['right_value']
        #     if type(left_value) == bool and type(right_value) == bool:
        #         return left_value | right_value
        #     else:
        #         raise Exception(f'left_variable {left_value} or right_value {right_value} has no operation or')

    def _get_variable_from_datasource(self, datasource, prop, input_params: dict, **kwargs) -> str:
        UID = kwargs.get('speaker_uid', None)
        if 'UID' in input_params:
            UID = kwargs.get(input_params.get('UID', ''), None)
        if UID is None:
            raise Exception(f"UID not found in input params {input_params} and kwargs {kwargs}")

        # 数据源的配置化先不做了，编码在这里
        if datasource == 'AI_basic_info':
            instance = InstanceMgr().get_instance_info(self.AID)
            if prop == 'nickname':
                return instance.get_nickname()
        elif datasource == 'AI_memory_of_user':
            mem_entity = HippocampusMgr().get_hippocampus(self.AID).load_memory_of_user(UID)
            if prop == 'user_name':
                name = mem_entity.get_target_name()
                if name == '':
                    name = UserInfoMgr().get_instance_info(UID).get_username()
                return name
            elif prop == 'intimacy_level':
                level = mem_entity.get_intimacy_level()
                return level
        elif datasource == 'user_info':
            user_info = UserInfoMgr().get_instance_info(UID)
            if prop == 'user_name':
                return user_info.get_username()
            elif prop == 'language':
                return user_info.get_user_language()


    def __init__(self, AID: str):
        self.tpl: Dict = {}
        self.redis_data: Dict[str, dict] = {}
        self.redis_hash_dict: Dict[str, str] = {}
        self._db_query_lock = threading.Lock()
        self.db_result = {}
        self.AID = AID
        self.redis_client = RedisClient()
        self.mongodb_client = MongoDBClient()
