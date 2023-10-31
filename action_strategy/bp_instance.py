import json
import logging
import queue
import re
from typing import Dict, Optional, List

from common_py.ai_toolkit.openAI import ChatGPTClient, Message
from common_py.model.base import BaseEvent
from common_py.model.chat import ConversationEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from opencensus.trace import execution_context

from action_strategy import const
from action_strategy.action import Action
from action_strategy.bp_router import RouterNode

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class BluePrintInstance:

    def __init__(self, action_queue: queue.Queue, bp_script):
        try:
            self.name = bp_script['name']
            self.description = bp_script['description']
            self.current_node = self._construct_blue_print(bp_script)
            self.action_queue = action_queue
            self.llm_client = ChatGPTClient(temperature=0)
            self.event_context: List[BaseEvent] = []
        except KeyError as e:
            logger.error(f"Missing key in blue print script: {e}")
            raise Exception("Missing key in blue print script")

    def _construct_blue_print(self, bp_script: Dict) -> str:
        """
        只能存在一个节点被设置为入口
        动作节点至多有一个出度，且出度只能指向路由节点
        路由节点至少有一个出度
        """
        self.nodes_collection = {}
        portal_node = None
        for node in bp_script['nodes']:
            if node['type'] == 'action':
                node_instance = self._construct_action_node(node)
            elif node['type'] == 'router':
                node_instance = self._construct_router_node(node)
            else:
                raise Exception("Unknown node type")
            if node_instance.is_portal_node:
                portal_node = node_instance.name
            self.nodes_collection[node['name']] = node_instance
        if portal_node is None:
            raise Exception("No portal node")
        return portal_node

    def _construct_router_node(self, node: Dict) -> RouterNode:
        """
        构建路由节点
        """
        rn = RouterNode(**node)
        return rn

    def _construct_action_node(self, node: Dict) -> Action:
        an = Action(**node)
        return an

    def execute(self, event: BaseEvent) -> str:
        try:
            node = self.nodes_collection.get(self.current_node)
            if isinstance(node, RouterNode):
                next_node_name = self._execute_router_script_node(node, event)
                next_node = self.nodes_collection.get(next_node_name, None)
                if isinstance(next_node, RouterNode):
                    self.current_node = next_node_name
                    return self.execute(event)
                elif isinstance(next_node, Action):
                    if next_node.pre_loading(event):
                        self.action_queue.put((next_node, event))
                        return next_node.next_node_name
        except Exception as e:
            # todo 退出蓝图
            logger.exception(e)
        finally:
            self.event_context.append(event)

    def execute_router(self, node: RouterNode, trigger_event: BaseEvent, **factor_values) -> str:
        if isinstance(trigger_event, ConversationEvent):
            if node.llm_router and node.llm_router != '':
                return self._execute_llm_router(node, trigger_event, **factor_values)
        if node.script_router and node.script_router != '':
            return self._execute_router_script_node(node, trigger_event, **factor_values)
        if node.llm_router and node.llm_router != '':
            return self._execute_llm_router(node, trigger_event, **factor_values)

    def _execute_router_script_node(self, node: RouterNode, event: BaseEvent, **factor_values) -> str:
        input_params = {
            'optional_child_node': node.child_node,
            'trigger_event': event,
            'tracer': execution_context.get_opencensus_tracer(),
            'next_node': '',
            **factor_values,
        }
        try:
            exec(node.script_router, input_params)
        except Exception as e:
            logger.exception(e)
            return ''
        return input_params['next_node']

    def _execute_llm_router(self, node: RouterNode, trigger_event: BaseEvent, **factor_values) -> str:
        mission_purpose = self.description
        known_conditions = ''
        for event in self.event_context:
            known_conditions += event.description() + '\n'
        child_nodes = node.child_node
        next_action_options = ''
        expected_output = ', '.join([node for node in child_nodes])
        for child_node in child_nodes:
            node = self.nodes_collection[child_node]
            # expected_output += f"{node.name},"
            next_action_options += f"""\nnode name: {node.name} \n node description: {node.description}\n"""

        prompt = const.router_prompt.format(mission_purpose=mission_purpose,
                                            known_conditions=known_conditions,
                                            expected_output=expected_output,
                                            next_action_options=next_action_options)
        resp = self.llm_client.generate(
            messages=[
                Message(role='system', content=prompt),
            ],
            UUID=trigger_event.UUID,
        )
        next_step = resp.get_chat_with_filter(extract_asterisks)
        logger.info(f"llm router response: {resp} and extract next step: {next_step}")
        if next_step in child_nodes:
            return next_step
        else:
            return ''


def extract_asterisks(s) -> str:
    # 使用正则表达式找到*之间的内容
    matches = re.findall(r'\*([^*]+)\*', s)
    # 将所有匹配的内容连接成一个字符串并返回
    return ' '.join(matches)
