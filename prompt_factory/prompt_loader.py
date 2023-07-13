import json
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

import yaml
import os

from common_py.client.pg import PgEngine
from common_py.client.pinecone_client import PineconeClient
from common_py.client.redis import RedisClient
from common_py.dto.ai_instance import AIBasicInformation
from sqlalchemy import text
from sqlalchemy.orm import Session

# emma_config = {}
# npc_config = {}
# tina_config = {}
os.chdir(os.path.dirname(__file__))
with open('tpl/emma.yml', 'r') as f:
    emma_config = yaml.safe_load(f)
with open('tpl/npc.yml', 'r') as f:
    npc_config = yaml.safe_load(f)
with open('tpl/tina.yml', 'r') as f:
    tina_config = yaml.safe_load(f)
specific_key = ['input', 'datasource']


class PromptLoader:

    def parse_prompt(self, **params) -> str:
        prompt_queue: queue.Queue = queue.Queue()
        variable_data = self._process_datasource(**params)
        with ThreadPoolExecutor(max_workers=5) as executor:
            idx = 0
            for tpl_name, tpl_block in self.tpl.items():
                if tpl_name in specific_key:
                    continue
                executor.submit(self._get_prompt_block, idx, tpl_block, prompt_queue, **variable_data)
                idx += 1
        res_list = []
        while not prompt_queue.empty():
            res_list.append(prompt_queue.get())
        # 按照 idx 从小到大排序
        sorted_lst = sorted(res_list, key=lambda x: x[0])

        # 将排序后的字符串通过 \n 连接起来
        result = '\n'.join([item[1] for item in sorted_lst])
        return result

    def _get_prompt_block(self, idx: int, tpl: dict, q: queue.Queue, **params):
        variables = tpl.get("variables", None)
        variable_res = {}
        if variables is not None:
            for key, variable in variables.items():
                if key in params:
                    variable_res[key] = params[key]
                    continue
                else:
                    if 'db_source' not in variable:
                        raise Exception(f"variable {key} has no db_source and can not found in redis")
                    if 'pg_table' not in self.datasource:
                        raise Exception(f"variable {key} has no pg_table and can not found in redis")
                    database_key = variable['db_source']
                    table, column_pair = database_key.split('#')[0], database_key.split('#')[1]
                    column_name, column_value = column_pair.split(':')[0], column_pair.split(':')[1]
                    if table in self.db_result:
                        table_res = self.db_result[table]
                        if column_name not in table_res:
                            raise Exception(f"column {column_name} not found in table {table}")
                        variable_res[key] = table_res[column_name]
                        continue
                    with self._db_query_lock:
                        if table not in self.db_result:
                            if table == "ai_instance":
                                with Session(self.pg_instance) as session:
                                    value = params.get(column_value, None)
                                    if value is None:
                                        raise Exception(f"column {column_value} not found in params")
                                    result = session.execute(text(f"select * from {table} where {column} = {value}"))
                                    rows = result.fetchall()
                                    if len(rows) == 0:
                                        raise Exception(f"ai_instance with id {params['aid']} not found")
                                    basic_information = AIBasicInformation(id=params['aid'])
                                    basic_information.load(session)
                                    self.db_result[table] = basic_information.dict()


    def _process_datasource(self, **params) -> dict:
        data_map = {}
        required_params: List[str] = self.tpl.get("input")
        for param in required_params:
            if param not in params:
                raise Exception(f"param {param} not found")
            data_map[param] = params[param]
        self.datasource = self.tpl.get("datasource")
        if "redis" in self.datasource:
            if type(self.datasource["redis"]) == list:
                for redis_key in self.datasource["redis"]:
                    redis_key.format(**data_map)
                    redis_res = self.redis_client.get(redis_key)
                    res_dict = json.loads(redis_res)
                    data_map.update(res_dict)
            elif type(self.datasource["redis"]) == str:
                redis_key = self.datasource["redis"].format(**data_map)
                redis_res = self.redis_client.get(redis_key)
                res_dict = json.loads(redis_res)
                data_map.update(res_dict)
        return data_map






    def __init__(self, tpl_type: str):
        self.tpl_type = tpl_type
        if tpl_type == "emma":
            self.tpl = emma_config
        elif tpl_type == "npc":
            self.tpl = npc_config
        elif tpl_type == "tina":
            self.tpl = tina_config
        self._db_query_lock = threading.Lock()
        self.db_result = {}
        self.redis_client = RedisClient()
        self.pinecone_client = PineconeClient()
        self.pg_instance = PgEngine().get_instance()

if __name__ == '__main__':
    dic = {'a': 123}
    print(dic['a'])