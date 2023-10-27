import queue
from typing import Dict, Optional

from action_strategy.bp_node import RouterNode, ActionNode


class BluePrintInstance:

    def __init__(self, bp_script: Dict, action_queue: queue.Queue):
        self.pending_node = self._construct_blue_print(bp_script, action_queue)

    def _construct_blue_print(self, bp_script: Dict, action_queue) -> Optional[RouterNode, ActionNode]:
        """
        只能存在一个节点被设置为入口
        动作节点至多有一个出度，且出度只能指向路由节点
        路由节点至少有一个出度
        """
        nodes_collection = {}
        for node in bp_script['nodes']:
            if node['type'] == 'action':
                nodes_collection[node['name']] = self._construct_action_node(node)
            elif node['type'] == 'router':
                nodes_collection[node['name']] = self._construct_router_node(node)
            else:
                raise Exception("Unknown node type")

    def _construct_router_node(self, node: Dict) -> RouterNode:
        """
        构建路由节点
        """
        rn = RouterNode(**node)
        return rn

    def _construct_action_node(self, node: Dict) -> ActionNode:
        an = ActionNode(**node)
        return an




