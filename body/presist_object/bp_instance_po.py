import logging
from typing import List, Dict

from common_py.client.azure_mongo import MongoDBClient
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler
from pydantic import BaseModel

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class NodeConnection(BaseModel):
    from_node: str
    to_node: str

    args_mapping: Dict[str, str]


class BluePrintPo(BaseModel):
    bp_id: str
    name: str
    description: str
    portal_node: str

    # type BpActionNode
    action_nodes: List[str]
    router_nodes: List[str]

    connections: NodeConnection    # 有向有环图

    # 暂时不支持蓝图挂蓝图
    # blue_print_nodes: List[str]


def load_all_bp_po() -> Dict[str, BluePrintPo]:
    mongodb_client = MongoDBClient()
    bp_po_dict = {}
    bp_lst = mongodb_client.find_from_collection("AI_blue_print", filter={})

    if not bp_lst:
        raise Exception("No blue print found")
    for bp in bp_lst:
        try:
            po = BluePrintPo(**bp)
            bp_po_dict[po.bp_id] = po
        except Exception as e:
            logger.exception(e)
            continue
    return bp_po_dict
