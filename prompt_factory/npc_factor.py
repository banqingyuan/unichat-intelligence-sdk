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
from common_py.const.ai_attr import AI_type_emma, AI_type_npc, Entity_type_user
from common_py.dto.ai_instance import AIBasicInformation
from common_py.utils.util import get_random_str
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from memory_sdk.memory_entity import AI_memory_source_id, AI_memory_target_id, AI_memory_target_type

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

    def create_new_AI(self, UID: str, TplName: str, profile: dict = None) -> str:
        TplName = TplName.lower()
        AID = self._gen(UID, TplName, profile)
        return AID

    def update_tpl_to_instance(self, tpl_name: str, latest_version: str, *fields):
        self._refresh_AI_tpl(tpl_name, latest_version, *fields)

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

    def _gen(self, UID: str, tpl_name: str, profile: dict = None) -> str:
        res = self.mongo_client.find_one_from_collection("AI_role_template", {"tpl_name": tpl_name})
        if not profile:
            profile = {}
        if not res:
            raise ValueError(f"No such AI personality: {AI_type_emma}")
        meta_data = res.get('meta_data', None)
        gender = res.get('gender', None)
        nickname = res.get('nickname', None)
        prompt_tpl = res.get('prompt_tpl', None)
        description = res.get('description', '')
        if not meta_data or not gender or not prompt_tpl:
            raise ValueError(f"Cannot find meta_data or gender or prompt_tpl of tpl {tpl_name}")
        avatar_id = meta_data.get('avatar_id', None)
        voice_id = meta_data.get('voice_id', None)
        typ = meta_data.get('role_type', None)
        version = meta_data.get('version', '1.0')
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
            "input": json.dumps(input_params),
            "datasource": json.dumps(datasource),
            "prompt_tpl": json.dumps(prompt_tpl),
            "tpl_name": tpl_name,
            "version": version,
            "description": description
        }
        if typ != AI_type_npc:
            ai_profile["UID"] = UID
            AID = _generate_AID(UID)
            partition_key = f"{AID}-{UID}"
            mem_entity = {
                '_partition_key': partition_key,
                AI_memory_source_id: AID,
                AI_memory_target_id: UID,
                AI_memory_target_type: Entity_type_user,
            }
            mem_entity.update()
            filter = {
                AI_memory_source_id: AID,
                AI_memory_target_id: UID,
                AI_memory_target_type: Entity_type_user,
            }
            self.mongo_client.update_many_document("AI_memory_reflection", filter, {'$set': mem_entity}, True)
        else:
            AID = _generate_NPC_AID()
        ai_profile["AID"] = AID
        self.redis_client.hset(RedisAIInstanceInfo.format(AID=AID), ai_profile)
        self.redis_client.expire(RedisAIInstanceInfo.format(AID=AID), 60 * 60 * 24 * 30)
        self.mongo_client.create_one_document("AI_instance", ai_profile)

        return AID

    def _refresh_AI_tpl(self, tpl_name: str, version: str, *fields):
        """
        缺失回滚手段
        """
        tpl_res = self.mongo_client.find_one_from_collection("AI_role_template", {"tpl_name": tpl_name})
        if not tpl_res:
            raise ValueError(f"Can not find tpl: {tpl_name}")

        update_fields = {}
        if 'voice_id' in fields:
            new_voice_id = tpl_res.get('meta_data', {}).get('voice_id', None)
            if not new_voice_id:
                raise ValueError(f"Can not find voice_id in tpl: {tpl_name}")
            update_fields['voice_id'] = new_voice_id
        if 'input' in fields:
            new_input = tpl_res.get('input', None)
            if not new_input:
                raise ValueError(f"Can not find input in tpl: {tpl_name}")
            update_fields['input'] = json.dumps(new_input)
        if 'datasource' in fields:
            new_datasource = tpl_res.get('datasource', None)
            if not new_datasource:
                raise ValueError(f"Can not find datasource in tpl: {tpl_name}")
            update_fields['datasource'] = json.dumps(new_datasource)
        if 'prompt_tpl' in fields:
            new_prompt_tpl = tpl_res.get('prompt_tpl', None)
            if not new_prompt_tpl:
                raise ValueError(f"Can not find prompt_tpl in tpl: {tpl_name}")
            update_fields['prompt_tpl'] = json.dumps(new_prompt_tpl)
        if 'description' in fields:
            new_description = tpl_res.get('description', None)
            if not new_description:
                raise ValueError(f"Can not find description in tpl: {tpl_name}")
            update_fields['description'] = new_description

        if len(update_fields) == 0:
            raise ValueError('input update_fields can not be empty')
        update_fields['version'] = version

        mongo_filter = {
            "tpl_name": tpl_name,
            "$or": [
                {"version": {"$ne": version}},
                {"version": {"$exists": False}}
            ]
        }

        docs = self.mongo_client.find_from_collection("AI_instance", filter=mongo_filter,
                                                        projection={"_id": 1, "AID": 1})

        if len(docs) == 0:
            return
        batch_ids = []
        batch_AIDS = []
        for doc in docs:
            batch_ids.append(doc['_id'])
            batch_AIDS.append(doc['AID'])

        mongo_result = self.mongo_client.update_many_document(
            "AI_instance",
            filter={"_id": {"$in": batch_ids}},
            update={'$set': update_fields}
        )
        logger.debug(f"update many document result {mongo_result}")

        for AID in batch_AIDS:
            ai_info = AIBasicInformation(AID=AID)
            ai_info.load_from_mongo(self.mongo_client)
            ai_info.set_to_redis(self.redis_client)

        # # 创建一个pipeline对象
        # pipeline = self.redis_client.pipeline()
        #
        # # 在pipeline中为每个AID执行hset操作
        # for AID in batch_AIDS:
        #     pipeline.hset(RedisAIInstanceInfo.format(AID=AID), mapping=update_fields)
        #
        # # 批量执行所有命令
        # pipeline.execute()

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


def _generate_NPC_AID() -> str:
    origin_str = f"{str(time.time())}_{get_random_str(6)}"
    md5 = hashlib.md5(origin_str.encode('utf-8')).hexdigest()
    return f"{md5[-10:]}"

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
