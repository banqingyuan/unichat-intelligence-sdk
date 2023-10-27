from typing import Dict, Optional

from common_py.model.base import BaseEvent


class RouterNode:
    """
    路由节点等待一个输入，这个输入应该是一个事件
    """
    def __init__(self, name, describe, child_node):
        self.name: str = name
        self.describe: str = describe
        self.condition_collect: Dict[str, str] = {}
        self.llm_router: Optional[Dict] = None
        self.script_router: Optional[Dict] = None
        self.child_node: Dict[str, Optional[ActionNode, RouterNode]] = child_node

    def eval(self, event: BaseEvent):
        if
