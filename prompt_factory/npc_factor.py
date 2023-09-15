import hashlib
import json
import random
import time

import os
import logging
import yaml
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.embedding import OpenAIEmbedding
from common_py.client.pg import PgEngine
from common_py.client.redis_client import RedisClient, RedisAIInstanceInfo
from common_py.const.ai_attr import AI_type_emma
from common_py.utils.util import get_random_str
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

os.chdir(os.path.dirname(__file__))
with open('tpl/firstname.yml', 'r') as f:
    firstname = yaml.safe_load(f)
with open('tpl/lastname.yml', 'r') as f:
    lastname = yaml.safe_load(f)


class NPCFactory:
    """
    ai_profile schema:
    {
        "AID": "AI instance id",
        "UID": "user id",
        "nickname": "nickname",
        "type": "AI type",
        "age": "age",
        "persona": "{}",
        "gender": "",
        "MBTI": "",
    }
    """

    def create_new_AI(self, UID: str, TplName: str) -> str:
        TplName = TplName.lower()
        AID = self._gen(UID, TplName)
        return AID

    # def _gen_tina(self, UID: str):
    #     AID = _generate_AID(UID)
    #     ai_profile = {
    #         "avatar_id": '1001',
    #         "voice_id": '6mOAa1TR13l2vZnlyUEV',
    #         "persona_id": '00000',
    #         "persona": "{}",
    #         "nickname": "Tina",
    #         "type": AI_type_tina,
    #         "UID": UID,
    #         "AID": AID,
    #         "gender": "female",
    #         "MBTI": "INTJ",
    #         "age": 25,
    #     }
    #     self.redis_client.hset(f"{RedisAIInstanceInfo}{AID}", ai_profile)
    #     self.redis_client.expire(f"{RedisAIInstanceInfo}{AID}", 60 * 60 * 24 * 30)
    #     return AID

    def _gen(self, UID: str, tpl_name: str):
        res = self.mongo_client.find_one_from_collection("AI_role_template", {"tpl_name": tpl_name})

        if not res:
            raise ValueError(f"No such AI personality: {AI_type_emma}")
        meta_data = res.get('meta_data', None)
        gender = res.get('gender', None)
        nickname = res.get('nickname', None)
        prompt_tpl = res.get('prompt_tpl', None)

        if not meta_data or not gender or not prompt_tpl:
            raise ValueError(f"Cannot find meta_data or gender or prompt_tpl of tpl {tpl_name}")
        avatar_id = meta_data.get('avatar_id', None)
        voice_id = meta_data.get('voice_id', None)
        typ = meta_data.get('role_type', None)
        if not typ or not avatar_id or not voice_id:
            raise ValueError(f"Cannot find avatar_id or voice_id or type or of tpl metadata {tpl_name}")

        res['_id'] = str(res['_id'])
        input_params = res.get('input', [])
        datasource = res.get('datasource', {})
        ai_profile = {
            "avatar_id": avatar_id,
            "voice_id": voice_id,
            "gender": gender,
            "nickname": nickname if nickname else _generate_random_name(gender=gender),
            "type": typ,
            "UID": UID,
            "input": json.dumps(input_params),
            "datasource": json.dumps(datasource),
            "prompt_tpl": json.dumps(prompt_tpl),
            "tpl_name": tpl_name,
        }
        AID = _generate_AID(UID)
        ai_profile["AID"] = AID
        self.redis_client.hset(f"{RedisAIInstanceInfo}{AID}", ai_profile)
        self.redis_client.expire(f"{RedisAIInstanceInfo}{AID}", 60 * 60 * 24 * 30)
        self.mongo_client.create_one_document("AI_instance", ai_profile)
        return AID

    # def persist_AI(self, AID: str):
    #     ai_profile = self.redis_client.hgetall(f"{RedisAIInstanceInfo}{AID}")
    #     if not ai_profile:
    #         raise ValueError(f"No such AI: {AID}")
    #     decode_profile = {k.decode('utf-8'): v.decode('utf-8') for k, v in ai_profile.items()}
    # def _match_prompt_tpl(self, persona_dict, provide_key, provide_value, ai_profile, ai_basic_info_list, no_use_list):
    #     if provide_key in persona_dict:
    #         description = persona_dict[provide_key]
    #         persona_dict.pop(provide_key)
    #         val = {
    #             # "description_embedding": self._get_embedding(input=description),
    #             # "content_embedding": self._get_embedding(input=provide_value),
    #             "description": description,
    #             "value": provide_value,
    #         }
    #         ai_profile["persona"][provide_key] = val
    #     elif provide_key in ai_basic_info_list:
    #         ai_basic_info_list.remove(provide_key)
    #         ai_profile[provide_key] = provide_value
    #     else:
    #         no_use_list.append(provide_key)

    # def _get_embedding(self, input: str):
    #     md5 = hashlib.md5(input.encode('utf-8')).hexdigest()
    #     key = f"embedding_of_{md5}"
    #     embedding_str = self.redis_client.get(key)
    #
    #     # Caching as a string causes the floating point numbers in the word vectors to lose precision,
    #     # leading to differences in the results of the comparison,
    #     # with a similarity gap of about 0.00001, which is acceptable
    #     if embedding_str is not None:
    #         self.redis_client.expire(key, 60 * 60 * 24 * 30)
    #         embedding = json.loads(embedding_str)
    #         return embedding
    #     embedding = self.embedding_client(input=input)
    #     embedding_cache = json.dumps(embedding)
    #     self.redis_client.setex(f"embedding_of_{md5}", embedding_cache, 60 * 60 * 24 * 30)
    #     return embedding

    def __init__(self):
        self.redis_client: RedisClient = RedisClient()
        self.mongo_client: MongoDBClient = MongoDBClient()
        self.embedding_client: OpenAIEmbedding = OpenAIEmbedding()
        self.pg_instance = PgEngine().get_instance()


def _generate_random_name(gender: str) -> str:
    if gender.lower() == 'female':
        return f"{random.choice(firstname['female'])} {random.choice(lastname)}"
    else:
        return f"{random.choice(firstname['male'])} {random.choice(lastname)}"


def _generate_AID(UID: str) -> str:
    # 对一个字段生成md5并截断保存后10位
    origin_str = f"{str(time.time())}_{get_random_str(6)}"
    md5 = hashlib.md5(origin_str.encode('utf-8')).hexdigest()
    return f"{UID}-{md5[-10:]}"

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
