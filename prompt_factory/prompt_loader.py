import json
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import md5
from typing import List, Dict

import os

from common_py.const.ai_attr import AI_type_emma, AI_type_passerby, AI_type_npc, AI_type_tina

from common_py.client.embedding import OpenAIEmbedding
from common_py.client.pg import PgEngine
from common_py.client.pinecone_client import PineconeClient
from common_py.client.redis import RedisClient
from common_py.utils.logger import logger
from common_py.utils.similarity import similarity

from prompt_factory.tpl_loader import emma_config, tina_config, npc_config

specific_key = ['input', 'datasource']


class PromptLoader:

    def parse_prompt(self, input: str, **params) -> str:
        prompt_queue: queue.Queue = queue.Queue()
        variable_data = self._process_datasource(**params)
        if "persona" in variable_data:
            variable_data.update(variable_data["persona"])
            variable_data.pop("persona")
        with ThreadPoolExecutor(max_workers=5) as executor:
            idx = 0
            for tpl_name, tpl_block in self.tpl.items():
                if tpl_name in specific_key:
                    continue
                executor.submit(self._get_prompt_block, idx, tpl_block, input, prompt_queue, **variable_data)
                idx += 1
        res_list = []
        while not prompt_queue.empty():
            res_list.append(prompt_queue.get())
        # 按照 idx 从小到大排序
        sorted_lst = sorted(res_list, key=lambda x: x[0])

        # 将排序后的字符串通过 \n 连接起来
        result = '\n'.join([item[1] for item in sorted_lst])
        return result

    def _get_prompt_block(self, idx: int, tpl: dict, chat_input: str, q: queue.Queue, **params):
        try:
            fixed_tpl = tpl.get("tpl", None)
            fixed_res = ""
            try:
                if fixed_tpl is not None:
                    # variables_res = self._get_variables_results(tpl, **params)
                    fixed_res = fixed_tpl.format(**params)
            except KeyError as e:
                logger.warning(f"variable not found when try to format tpl :{fixed_tpl}. key: {e}")

            reflection = tpl.get("reflection", None)
            if reflection is None:
                q.put((idx, fixed_res))
                return
            reflection_res = self._get_reflection_results(reflection, chat_input, **params)
            q.put((idx, fixed_res + '\n' + reflection_res))
        except Exception as e:
            logger.exception(e)

    def _get_reflection_results(self, reflection, chat_input, **params) -> str:
        # Calculating the similarity of two 1536-dimensional vectors takes on average 1ms
        accepted_reflection = {}
        chat_embedding = OpenAIEmbedding()(input=chat_input)
        top_3_of_description = []
        top_3_of_content = []
        for reflection_name, reflection_source in reflection.items():
            reflection_res = params.get(reflection_name, None)
            if reflection_res is None:
                if "vector_database" in reflection_source:
                    accepted_reflection[reflection_name] = self._get_vector_database(reflection_source["vector_database"], chat_embedding, **params)
                continue
            reflection_description_embedding = reflection_res.get('description_embedding', None)
            reflection_content_embedding = reflection_res.get('content_embedding', None)
            reflection_value = reflection_res.get('value', None)

            description_similarity = similarity(chat_embedding, reflection_description_embedding)
            content_similarity = similarity(chat_embedding, reflection_content_embedding)

            self._maintain_top3(top_3_of_description, (description_similarity, reflection_name, reflection_value))
            self._maintain_top3(top_3_of_content, (content_similarity, reflection_name, reflection_value))
        for item in top_3_of_content:
            accepted_reflection[item[1]] = item[2]
        for item in top_3_of_description:
            accepted_reflection[item[1]] = item[2]
        reflection_str = '\n'.join([f'{value}' for value in accepted_reflection.values()])
        return reflection_str

    def _get_vector_database(self, vdb_info, chat_embedding: List[float], **params) -> str:
        namespace = vdb_info.get('namespace', None)
        metadata = vdb_info.get('metadata', None)
        topK = vdb_info.get('top', 2)
        if namespace is None or metadata is None or len(metadata) == 0:
            return ""
        query_dict = {}
        if len(metadata) > 1:
            query_list = []
            for meta_item in metadata:
                query_list.append(self._parse_single_metadata(meta_item, **params))
            query_dict['$and'] = query_list
        else:
            query_dict = self._parse_single_metadata(metadata[0], **params)
        logger.debug(f"query from vector database with namespace {namespace}, filter: {query_dict}")
        resp = self.pinecone_client.query_index(namespace=namespace, vector=chat_embedding, top_k=topK, filter=query_dict, include_metadata=True)
        if 'matches' not in resp:
            return ""
        vec_res = []
        for match in resp['matches']:
            if 'metadata' not in match:
                continue
            metadata = match['metadata']
            if 'blob_name' not in metadata:
                continue
            blob_name = metadata['blob_name']
            # cache in redis use blob_name as key
            data = self.redis_client.get(blob_name)
            vec_res.append(data)
        return '\n'.join(vec_res)

    def _maintain_top3(self, top3_list: List, item: tuple):
        if len(top3_list) < 3:
            top3_list.append(item)
        else:
            min_index = min(enumerate(top3_list), key=lambda x: x[1][0])[0]
            if item[0] > top3_list[min_index][0]:
                top3_list[min_index] = item
        top3_list.sort(key=lambda x: x[0], reverse=True)
        return top3_list

    def _get_variables_results(self, tpl: dict, **params) -> dict:
        variables = tpl.get("variables", None)
        variable_res = {}
        if variables is not None:
            for key, variable in variables.items():
                # looking for redis cache, if not cached, then query from pg if pg source exists
                if key in params:
                    variable_res[key] = params[key]
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

    def _process_datasource(self, **params) -> dict:
        data_map = {}
        required_params: List[str] = self.tpl.get("input")
        for param in required_params:
            if param not in params:
                raise Exception(f"param {param} not found")
        data_map.update(params)
        logger.debug(f"process datasource with params {params.keys()}")
        self.datasource = self.tpl.get("datasource")
        if "redis" in self.datasource:
            for redis_key_tpl, redis_detail in self.datasource["redis"].items():
                redis_key = redis_key_tpl.format(**data_map)
                # hash_key = '_'.join([redis_key, "hash"])
                # hash_res = self.redis_client.get(hash_key)
                # if hash_res is None:
                #     logger.warning(f"redis_key {redis_key} has no hash key")
                # elif hash_key in self.redis_hash_dict and self.redis_hash_dict[hash_key] == hash_res:
                if redis_key in self.redis_data:
                    data_map.update(self.redis_data[redis_key])
                    continue

                redis_data = {}
                if redis_detail["method"] == "hmget":
                    if redis_detail["keymap"] is None:
                        raise Exception(f"keymap not found in redis detail {redis_detail}")
                    keymap = redis_detail["keymap"]
                    if type(keymap) is not dict:
                        raise Exception(f"keymap should be a dict")
                    redis_res = self.redis_client.hmget(redis_key, keymap.keys())
                    for key, value in zip(keymap.keys(), redis_res):
                        redis_data[keymap[key]] = value
                else:
                    raise Exception(f"redis method {redis_detail['method']} not supported")
                if redis_data is None:
                    logger.warning(f"failed to load redis_key {redis_key} cause redis key not found")
                    continue
                self.redis_data[redis_key] = redis_data
                # if hash_res is not None:
                #     self.redis_hash_dict[hash_key] = hash_res
                # else:
                #     # 如果从来没有设置过hash，说明写入方不支持，在这里帮忙hash一下
                #     hash_val = md5(json.dumps(redis_data).encode('utf-8')).hexdigest()
                #     self.redis_client.set(hash_key, hash_val)
                #     self.redis_hash_dict[hash_key] = hash_val
                data_map.update(redis_data)
        return data_map

    def _parse_single_metadata(self, meta_item: str, **params):
        meta_elements = meta_item.split(':')
        if len(meta_elements) != 3:
            raise Exception(f"metadata {meta_item} has wrong format")
        meta_name, operator, meta_value_tpl = meta_elements[0], meta_elements[1], meta_elements[2]
        meta_value = meta_value_tpl.format(**params)
        query_dict = {}
        if operator == 'contain':
            value_list = meta_value.split(',')
            query_dict[meta_name] = {'$in': value_list}
        elif operator == 'equal':
            query_dict[meta_name] = meta_value
        else:
            raise Exception(f"vector database operator {operator} not support yet")
        return query_dict

    def __init__(self, tpl_type: str):
        self.tpl_type = tpl_type
        if tpl_type == AI_type_emma or tpl_type == AI_type_passerby:
            self.tpl = emma_config
        elif tpl_type == AI_type_npc:
            self.tpl = npc_config
        elif tpl_type == AI_type_tina:
            self.tpl = tina_config
        self.redis_data: Dict[str, dict] = {}
        self.redis_hash_dict: Dict[str, str] = {}
        self._db_query_lock = threading.Lock()
        self.db_result = {}
        self.redis_client = RedisClient()
        self.pinecone_client = PineconeClient()
