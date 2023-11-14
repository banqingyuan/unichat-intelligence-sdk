import logging
import threading
import uuid
from typing import Dict, Optional, List
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from body.entity.function_call import FunctionDescribe
from body.presist_object.bp_router_po import load_all_bp_router_po, BPRouterPo

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

# 路由节点可以免配置，但是会生成一个独立的匿名节点，允许后续的节点连接和当前节点自定义
RouterType_Anonymous = "anonymous"
RouterType_Customize = "customize"


class RouterNode(FunctionDescribe):
    """
    路由节点等待一个输入，这个输入应该是一个事件
    路由节点能力的三个递进步骤
    1. 根据固定的已有条件，构造路由prompt，模板是固定的，参数是根据上下文组合的。因此用户不需要对Router进行任何配置。
    2. 一方编辑工具，编写脚本进行路由。todo 需要进一步设计。在这一版本实现一个简单点的。
    3. 用户设计，支持通过条件表达式控制路由。类似规则引擎
    """
    id: str
    router_type: str = RouterType_Anonymous
    router_name: str
    script_router: Optional[str] = None
    child_node_ids: Dict[str, List[str]]


class BPRouterManager:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            BPRouterManager._ready = True
            self.bp_router_dict: Dict[str, BPRouterPo] = {}
            self.refresh()

    def refresh(self):
        self.bp_router_dict = load_all_bp_router_po()
        threading.Timer(60*2, self.refresh).start()

    def get_router(self, router_id: str) -> Optional[RouterNode]:
        if router_id not in self.bp_router_dict:
            logger.error(f"Router {router_id} not found")
            return None
        router_po = self.bp_router_dict[router_id]
        router = RouterNode(
            script_router=router_po.script_router,
            id=router_po.router_id,
            router_name=router_po.router_name,
            router_type=router_po.router_type,
            child_node_ids=router_po.child_node_ids
        )
        return router

    def __new__(cls, *args, **kwargs):
        if not hasattr(BPRouterManager, "_instance"):
            with BPRouterManager._instance_lock:
                if not hasattr(BPRouterManager, "_instance"):
                    BPRouterManager._instance = object.__new__(cls)
        return BPRouterManager._instance

