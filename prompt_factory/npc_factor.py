import hashlib
import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from copy import copy
import yaml
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.embedding import OpenAIEmbedding
from common_py.client.redis import RedisClient, RedisAIInstanceInfo
from common_py.utils.util import get_random_str

import tpl_loader

with open('tpl/firstname.yml', 'r') as f:
    firstname = yaml.safe_load(f)
with open('tpl/lastname.yml', 'r') as f:
    lastname = yaml.safe_load(f)


class NPCFactory:

    def create_new_tmp_AI(self, typ: str, UID: str, **kwargs) -> str:
        exclude_personality_ids = kwargs.get('exclude_personality_ids', [])
        res = self.mongo_client.aggregate_from_collection("AI_personality", [
            {"$match": {"type": typ, "id": {"$nin": exclude_personality_ids}}},
            {"$sample": {"size": 1}}
        ])
        if len(res) == 0:
            raise ValueError(f"No such AI personality: {typ}")
        personality = res[0]
        ai_profile = {}
        if typ == 'emma':
            tpl_persona_dict = copy(tpl_loader.emma_personality_dict)
            ai_basic_info_list = copy(tpl_loader.emma_basic_info)
        elif typ == 'npc':
            tpl_persona_dict = copy(tpl_loader.npc_personality_dict)
            ai_basic_info_list = copy(tpl_loader.npc_basic_info)
        elif typ == 'tina':
            tpl_persona_dict = copy(tpl_loader.tina_personality_dict)
            ai_basic_info_list = copy(tpl_loader.tina_basic_info)
        else:
            raise ValueError(f"Unknown AI type: {typ}")
        ai_profile["persona"] = {}

        no_use_list = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            for k, v in personality.items():
                executor.submit(self._match_prompt_tpl, tpl_persona_dict, k, v, ai_profile, ai_basic_info_list, no_use_list)

        if len(no_use_list) > 0:
            logging.warning("useless personality: %s", no_use_list)
        if len(tpl_persona_dict) > 0:
            logging.warning("missing personality: %s", tpl_persona_dict.keys())
        ai_profile["nickname"] = _generate_random_name(gender=ai_profile["gender"])
        ai_profile["type"] = typ if typ != 'emma' else 'passerby'
        ai_profile["UID"] = UID
        AID = _generate_AID(UID)
        ai_profile["AID"] = AID
        self.redis_client.hset(f"{RedisAIInstanceInfo}{AID}", ai_profile)
        self.redis_client.expire(f"{RedisAIInstanceInfo}{AID}", 60 * 60 * 24 * 30)
        return AID

    def _match_prompt_tpl(self, persona_dict, provide_key, provide_value, ai_profile, ai_basic_info_list, no_use_list):
        if provide_key in persona_dict:
            description = persona_dict[provide_key]
            persona_dict.pop(provide_key)
            val = {
                "description_embedding": self._get_embedding(input=description),
                "content_embedding": self._get_embedding(input=provide_value),
                "value": provide_value,
            }
            ai_profile["persona"][provide_key] = val
        elif provide_key in ai_basic_info_list:
            ai_basic_info_list.remove(provide_key)
            ai_profile[provide_key] = provide_value
        else:
            no_use_list.append(provide_key)

    def _get_embedding(self, input: str):
        md5 = hashlib.md5(input.encode('utf-8')).hexdigest()
        key = f"embedding_of_{md5}"
        embedding_str = self.redis_client.get(key)

        # Caching as a string causes the floating point numbers in the word vectors to lose precision,
        # leading to differences in the results of the comparison,
        # with a similarity gap of about 0.00001, which is acceptable
        if embedding_str is not None:
            self.redis_client.expire(key, 60*60*24*30)
            embedding = json.loads(embedding_str)
            return embedding
        embedding = self.embedding_client(input=input)
        embedding_cache = json.dumps(embedding)
        self.redis_client.setex(f"embedding_of_{md5}", embedding_cache, 60*60*24*30)
        return embedding

    def __init__(self, redis_client, mongodb_client):
        self.redis_client: RedisClient = redis_client
        self.mongo_client: MongoDBClient = mongodb_client
        self.embedding_client: OpenAIEmbedding = OpenAIEmbedding()


def _generate_random_name(gender: str) -> str:
    if gender.lower() == 'female':
        return f"{random.choice(firstname['female'])} {random.choice(lastname)}"
    else:
        return f"{random.choice(firstname['male'])} {random.choice(lastname)}"


def _generate_AID(UID: str) -> str:
    # 对一个字段生成md5并截断保存后10位
    origin_str = f"{str(time.time())}_{get_random_str(6)}"
    md5 = hashlib.md5(origin_str.encode('utf-8')).hexdigest()
    return f"{UID}_{md5[-10:]}"


# if __name__ == '__main__':
#     redis_config = {
#         "host": "unichat-east.redis.cache.windows.net",
#         "port": "6380",
#         "ssl": True
#     }
#     password = os.environ.get("AZURE_REDIS_PASSWORD")
#     RedisClient(**redis_config, password=password)
#
#     mongo_client = MongoDBClient(DB_NAME="unichat-backend")
#     npc_factory = NPCFactory(redis_client=RedisClient(), mongodb_client=mongo_client)
#     # npc_factory.create_new_tmp_AI(typ='emma', UID='test')
#     time1 = time.time()
#     embedding = npc_factory._get_embedding("hello xiaohong")
#     time2 = time.time()
#     print(time2 - time1)
#     embedding2 = OpenAIEmbedding()(input="hello motor")
#     print(similarity(embedding, embedding2))