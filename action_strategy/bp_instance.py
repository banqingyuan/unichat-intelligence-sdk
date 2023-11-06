import logging
import queue
import re
from typing import Dict, Optional, List

from common_py.ai_toolkit.openAI import ChatGPTClient, Message, OpenAIChatResponse
from common_py.model.base import BaseEvent
from common_py.model.chat import ConversationEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from opencensus.trace import execution_context

from action_strategy import const
from action_strategy.base_action import BaseAction, BpActionNode
from action_strategy.bp_router import RouterNode
from action_strategy.function_call import FunctionDescribe

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class FunctionCallException(Exception):
    pass


class BluePrintInstance:

    def __init__(self, channel_name, bp_script):
        try:
            self.name = bp_script['name']
            self.description = bp_script['description']
            self.current_node = bp_script['portal_node']
            self.access_level: str = bp_script.get('access_level', 'public')
            self.AI_type: List[str] = bp_script['AI_type']
            self.channel_name = channel_name
            self.nodes_collection: Dict = {}
            self._construct_blue_print(bp_script)
            self.action_queue: Optional[queue.Queue] = None
            self.llm_client = ChatGPTClient(temperature=0)
            self.event_context: List[BaseEvent] = []
        except KeyError as e:
            logger.error(f"Missing key in blue print script: {e}")
            raise Exception("Missing key in blue print script")

    def init(self, action_queue: queue.Queue, context_event: List[BaseEvent]):
        self.action_queue = action_queue
        self.event_context.append(*context_event)

    def _construct_blue_print(self, bp_script: Dict):
        """
        只能存在一个节点被设置为入口
        动作节点至多有一个出度，且出度只能指向路由节点
        路由节点至少有一个出度
        """
        for node in bp_script['nodes']:
            if node['type'] == 'action':
                node_instance = self._construct_action_node(node)
            elif node['type'] == 'router':
                node_instance = self._construct_router_node(node)
            else:
                raise Exception("Unknown node type")
            self.nodes_collection[node['name']] = node_instance

    def _construct_router_node(self, node: Dict) -> RouterNode:
        """
        构建路由节点
        """
        rn = RouterNode(**node)
        return rn

    def _construct_action_node(self, node: Dict) -> BpActionNode:
        an = BpActionNode(**node)
        return an

    def execute(self, event: BaseEvent) -> str:
        try:
            node = self.nodes_collection.get(self.current_node)
            if isinstance(node, RouterNode):
                next_node = self._execute_router(node, event)
                if isinstance(next_node, RouterNode):
                    self.current_node = next_node
                    return self.execute(event)
                elif isinstance(next_node, BpActionNode):
                    # 在蓝图中进入Action节点，不需要前置判断
                    # if next_node.pre_loading(event):
                    self.action_queue.put((next_node, event))
                    self.current_node = next_node
                    return next_node.next_node_name
            if isinstance(node, BpActionNode):
                self.action_queue.put((node, event))
                self.current_node = node
                return node.next_node_name
        except Exception as e:
            # todo 退出蓝图
            logger.exception(e)
            return ''
        finally:
            self.event_context.append(event)

    def _execute_router(self, node: RouterNode, trigger_event: BaseEvent, **factor_values) -> str:
        if isinstance(trigger_event, ConversationEvent):
            if node.llm_router and node.llm_router != '':
                return self._execute_llm_router(node, trigger_event, **factor_values)
        shared_conditions = ''
        if node.script_router and node.script_router != '':
            next_node, shared_conditions = self._execute_router_script_node(node, trigger_event, **factor_values)
            if next_node != '':
                return next_node
        factor_values.update({'shared_conditions': shared_conditions})
        if node.llm_router and node.llm_router != '':
            return self._execute_llm_router(node, trigger_event, **factor_values)

    def _execute_router_script_node(self, node: RouterNode, event: BaseEvent, **factor_values) -> (
            FunctionDescribe, str):
        input_params = {
            'optional_child_node': node.child_node,
            'trigger_event': event,
            'tracer': execution_context.get_opencensus_tracer(),
            'next_node': None,
            'shared_conditions': '',
            **factor_values,
        }
        try:
            exec(node.script_router, input_params)
        except Exception as e:
            logger.exception(e)
            return ''
        return input_params['next_node'], input_params['shared_conditions']

    def _execute_llm_router(self, node: RouterNode, trigger_event: BaseEvent, **factor_values) -> str:
        mission_purpose = self.description
        known_conditions = ''
        for event in self.event_context:
            known_conditions += event.description() + '\n'
        if 'shared_conditions' in factor_values:
            known_conditions += factor_values['shared_conditions'] + '\n'
        child_nodes = node.child_node

        functions = []
        for child_node in child_nodes:
            node = self.nodes_collection[child_node]
            # expected_output += f"{node.name},"
            functions.append(node.gen_function_call_describe())

        prompt = const.router_prompt.format(
            mission_purpose=mission_purpose,
            known_conditions=known_conditions,
        )
        resp = self.llm_client.generate(
            messages=[
                Message(role='system', content=prompt),
            ],
            UUID=trigger_event.UUID,
            functions=functions,
        )
        if isinstance(resp, OpenAIChatResponse):
            if resp.function_name is not None and resp.function_name != '':
                function_call_tmp = self.nodes_collection.get(resp.function_name, None)
                if function_call_tmp is None:
                    raise FunctionCallException(f"Function {resp.function_name} not found with response {resp.json()}")
                function_call_copy = function_call_tmp.copy(deep=True)
                args = resp.arguments
                args.update(
                    trigger_event=trigger_event,
                )
                function_call_copy.set_args(**args)
                logger.info(f"llm router response: {resp.json()} and extract next step: {resp.function_name}")
                return function_call_copy
            else:
                raise FunctionCallException(f"Function name is empty with response {resp.json()}")
        else:
            raise FunctionCallException(f"Function call failed with response {resp.json()}")


def extract_asterisks(s) -> str:
    # 使用正则表达式找到*之间的内容
    matches = re.findall(r'\*([^*]+)\*', s)
    # 将所有匹配的内容连接成一个字符串并返回
    return ' '.join(matches)
