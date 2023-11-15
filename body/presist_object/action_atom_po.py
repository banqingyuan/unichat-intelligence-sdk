from common_py.client.azure_mongo import MongoDBClient
from pydantic import BaseModel
from typing import List, Dict
import logging
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler

from body.entity.function_call import Parameter

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class ActionAtomPo(BaseModel):
    # 同一种动作，在不同的编排中的id都是不同的，但只需保证全剧本中唯一即可。
    atom_id: str
    # 动作名称，用于区分不同的动作，但是也和动作种类没有关系，可以任意自定义，在剧本中唯一.
    atom_name: str
    atom_description: str

    # action 类型 用于区分不同的动作模板
    action_type: str

    # 用户填写的常量参数
    action_preset_args: Dict[str, str] = None


def load_all_action_atom_po() -> Dict[str, ActionAtomPo]:
    """
    从配置文件中加载所有的动作原子
    :return:
    """
    mongo_client = MongoDBClient()
    action_atom_pos = mongo_client.find_from_collection("AI_action_atom", filter={})
    if not action_atom_pos:
        raise Exception("No action atom found")
    action_atom_dict = {}
    for action_atom_po in action_atom_pos:
        try:
            po = ActionAtomPo(**action_atom_po)
            action_atom_dict[po.atom_id] = po
        except Exception as e:
            logger.exception(e)
            continue
    return action_atom_dict
