import logging
from typing import List, Dict

from common_py.client.azure_mongo import MongoDBClient
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler
from pydantic import BaseModel

from body.entity.function_call import Parameter

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class ActionProgramPo(BaseModel):
    program_id: str
    program_name: str
    description: str

    # 所有存放的节点id
    action_nodes: List[str]

    # 通过id索引的，上一个动作的id 通过索引构成的有向无环图
    action_graph: Dict[str, str]
    args_input: Parameter = None
    args_output: Parameter = None


def load_all_action_program_po() -> Dict[str, ActionProgramPo]:
    """
    从配置文件中加载所有的动作原子
    :return:
    """
    mongo_client = MongoDBClient()
    program_dict = {}
    programs = mongo_client.find_from_collection("AI_action_programs", filter={})
    if not programs or len(programs) <= 0:
        logger.info("No action program in AI_action_programs collection.")
        return program_dict
    program_dict = {}
    for program in programs:
        try:
            program_po = ActionProgramPo(**program)
            program_dict[program_po.program_id] = program_po
        except Exception as e:
            logger.info(f"load all action program got exception {e}")
            continue
    return program_dict
