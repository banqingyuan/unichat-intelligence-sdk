import logging
from typing import List, Dict

from common_py.client.azure_mongo import MongoDBClient
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from pydantic import BaseModel

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


# 这个节点的可复用性会比较差
class BPRouterPo(BaseModel):
    router_id: str
    router_name: str
    description: str
    router_type: str = None
    script_router: str = None


def load_all_bp_router_po() -> Dict[str, BPRouterPo]:
    mongodb_client = MongoDBClient()
    bp_router_po_dict = {}
    bp_router_lst = mongodb_client.find_from_collection("AI_bp_router", filter={})

    if not bp_router_lst:
        raise Exception("No blue print router found")
    for bp_router in bp_router_lst:
        try:
            po = BPRouterPo(**bp_router)
            bp_router_po_dict[po.router_id] = po
        except Exception as e:
            logger.exception(e)
            continue
    return bp_router_po_dict
