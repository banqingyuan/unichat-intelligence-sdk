from typing import Optional, Dict
from common_py.client.azure_mongo import MongoDBClient
from pydantic import BaseModel
import logging
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler


logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class ActionNodePo(BaseModel):

    node_id: str
    queuing_time: str = '1'
    system_prompt: Optional[str] = None
    preset_args: Optional[Dict[str, str]] = None

    node_name: str

    # action_program 以后是由无代码拖拽生成，类似scratch
    action_type: str
    action_id: str
    description: str


def load_all_action_node_po() -> Dict[str, ActionNodePo]:
    """
    加载所有的动作节点
    :return:
    """
    mongo_client = MongoDBClient()
    action_node_pos = mongo_client.find_from_collection("AI_action_node", filter={})
    if not action_node_pos:
        raise Exception("No action node found")
    action_node_dict = {}
    for action_node_po in action_node_pos:
        try:
            node = ActionNodePo(**action_node_po)
            action_node_dict[node.node_id] = node
        except Exception as e:
            logger.exception(e)
            continue
    return action_node_dict
