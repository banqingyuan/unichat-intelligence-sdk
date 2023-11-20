import logging
import queue
import threading
from typing import Dict, Optional, List, Union

from common_py.ai_toolkit.openAI import ChatGPTClient, Message, OpenAIChatResponse
from common_py.client.azure_mongo import MongoDBClient
from common_py.model.base import BaseEvent
from common_py.model.chat import ConversationEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from opencensus.trace import execution_context

from body import const
from body.blue_print.bp_router import RouterNode, BPRouterManager
from body.const import BPNodeType_Action, BPNodeType_Router
from body.entity.action_node import ActionNode, ActionNodeMgr
from body.entity.function_call import FunctionDescribe, Parameter
from body.presist_object.bp_instance_po import load_all_bp_po, BluePrintPo

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class FunctionCallException(Exception):
    pass


class BluePrintInstance:

    """
    bp_id: str
    name: str
    description: str
    portal_node: str

    # type BpActionNode
    action_nodes: List[str]
    router_nodes: List[str]

    connections: NodeConnection    # 有向有环图

    蓝图节点之间在衔接的时候，存在商订的入参和出参。
    当两个节点产生连接，需要配置好上游出参和下游入参的映射关系，保持类型一致。
    一种例外的情况是，如果上游最后一步是function call, 只需要下游提供入参标准，上游映射由llm完成
    """
    def __init__(self, **bp_po):
        try:
            self.bp_id = bp_po['bp_id']
            self.name = bp_po['name']
            self.description = bp_po['description']
            self.current_node = bp_po['portal_node']

            # key is node_id, value is node type
            self.nodes_typ_idx: Dict[str, str] = {}

            # eg. {'上游节点id', {'下游节点id', {'上游出参': '下游入参'}}}
            self.connection_mapping: Dict[str, Dict[str, Dict[str, str]]] = bp_po['connections']

            self._construct_blue_print(bp_po)
            self.action_queue: Optional[queue.Queue] = None
            self.llm_client = ChatGPTClient(temperature=0)
            self.event_context: List[BaseEvent] = []
        except KeyError as e:
            logger.error(f"Missing key in blue print script: {e}")
            raise Exception("Missing key in blue print script")

    def init(self, action_queue: queue.Queue, context_event: List[BaseEvent]):
        self.action_queue = action_queue
        self.event_context.append(*context_event)

    def _construct_blue_print(self, bp_po: Dict):
        """
        只能存在一个节点被设置为入口
        动作节点至多有一个出度，且出度只能指向路由节点
        路由节点至少有一个出度
        """
        for node in bp_po['action_nodes']:
            self.nodes_typ_idx[node['id']] = BPNodeType_Action
        for node in bp_po['router_nodes']:
            self.nodes_typ_idx[node['id']] = BPNodeType_Router

    def execute(self, event: BaseEvent) -> str:
        try:
            node = self.current_node
            if isinstance(node, RouterNode):
                next_node_id, params = self._execute_router(node, event)
                next_node = self._get_node_instance(next_node_id)
                next_node.set_params(**params.dict())
                if isinstance(next_node, RouterNode):
                    self.current_node = next_node
                    return self.execute(event)
                elif isinstance(next_node, ActionNode):
                    # 在蓝图中进入Action节点，不需要前置判断
                    # if next_node.pre_loading(event):
                    self.action_queue.put((next_node, event))
                    next_router_node = self._get_child_node_of_action_node(next_node.id)
                    if not next_router_node:
                        return ''
                    self.current_node = next_router_node
                    return self.current_node.id
            if isinstance(node, ActionNode):
                self.action_queue.put((node, event))
                next_node = self._get_child_node_of_action_node(node.id)
                if not next_node:
                    return ''
                self.current_node = next_node
                return next_node.id
        except Exception as e:
            # todo 退出蓝图
            logger.exception(e)
            return ''

    def add_event_context(self, event: BaseEvent):
        self.event_context.append(event)


    def _execute_router(self, node: RouterNode, trigger_event: BaseEvent) -> (str, Parameter):
        # 首先判断是否使用脚本路由，如果不使用，默认使用llm路由
        # 如果是conversation event, 暂不支持使用脚本路由
        # todo 脚本路由实现
        if isinstance(trigger_event, ConversationEvent):
            return self._execute_llm_router(node, trigger_event)
        shared_conditions = ''
        if node.script_router and node.script_router != '':
            # script 既可以直接进行route操作，也可以作为llm的补充【通过设置shared_conditions来实现】
            next_node, shared_conditions, params = self._execute_router_script_node(node, trigger_event)
            if next_node != '':
                return next_node, params
        return self._execute_llm_router(node, trigger_event, shared_conditions)

    def _execute_router_script_node(self, node: RouterNode, event: BaseEvent) -> (str, str, Parameter):
        nodes = self._get_all_child_node_id(node.id)
        input_params = {
            'optional_child_node': nodes,
            'trigger_event': event,
            'tracer': execution_context.get_opencensus_tracer(),
            'next_node': None,
            'output_args_dict': {},
            'shared_conditions': '',
        }
        try:
            exec(node.script_router, input_params)
        except Exception as e:
            logger.exception(e)
            return ''

        if len(input_params['output_args_dict']) > 0:
            output_params = Parameter(**input_params['output_args_dict'])
        else:
            output_params = None
        return input_params['next_node'], input_params['shared_conditions'], output_params

    def _execute_llm_router(self, router: RouterNode, trigger_event: BaseEvent, shared_conditions: str = None) -> (str, Parameter):
        mission_purpose = self.description
        known_conditions = ''
        for event in self.event_context:
            known_conditions += event.description() + '\n'
        if shared_conditions:
            known_conditions += shared_conditions + '\n'
        child_nodes = self._get_all_child_node_id(router.id)

        functions = []
        function_name_to_instance = {}
        for child_node_id in child_nodes:
            node_instance = self._get_node_instance(child_node_id)
            function_name_to_instance[node_instance.name] = node_instance
            # expected_output += f"{node.name},"
            functions.append(node_instance.gen_function_call_describe())

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
                func = function_name_to_instance.get(resp.function_name, None)
                if not func:
                    raise FunctionCallException(f"Function name {resp.function_name} not found with response {resp.json()}")
                if resp.arguments and len(resp.arguments) > 0:
                    func.set_params(**resp.arguments)
                # params 的引用持有不会影响到func的释放
                params = func.parameters
                return func.id, params
            else:
                raise FunctionCallException(f"Function name is empty with response {resp.json()}")
        else:
            raise FunctionCallException(f"Function call failed with response {resp.json()}")

    def _get_child_node_of_action_node(self, node_id) -> Optional[RouterNode]:
        next_round_node_id = self._get_all_child_node_id(node_id)
        if len(next_round_node_id) == 0:
            return None
        elif len(next_round_node_id) > 1:
            logger.error(f"Action Node should not have more than one child node: {node_id}")
            return None
        next_round_node = self._get_node_instance(next_round_node_id[0])
        if not isinstance(next_round_node, RouterNode):
            logger.error(f"Next round node should be router node: {next_round_node.id}")
            return None
        return next_round_node

    def _get_all_child_node_id(self, node_id: str) -> List[str]:
        nodes = []
        child_node_ids = self.connection_mapping[node_id].keys()
        for child_node_id in child_node_ids:
            nodes.append(child_node_id)
        return nodes

    def _get_node_instance(self, node_id: str) -> Union[RouterNode, ActionNode]:
        node_typ = self.nodes_typ_idx[node_id]
        if node_typ == BPNodeType_Action:
            node = ActionNodeMgr().get_action_node(node_id)
        elif node_typ == BPNodeType_Router:
            node = BPRouterManager().get_router(node_id)
        else:
            raise Exception("Unknown node type")
        return node


class BluePrintManager:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            BluePrintManager._ready = True
            self.bp_po_dict: Dict[str, BluePrintPo] = {}
            self.refresh()

    def refresh(self):
        try:
            self.bp_po_dict = load_all_bp_po()
        except Exception as e:
            logger.exception(e)
        threading.Timer(120, self.refresh).start()

    def get_instance(self, bp_id: str) -> Optional[BluePrintInstance]:
        try:
            bp_po = self.bp_po_dict.get(bp_id, None)
            if not bp_po:
                logger.error(f"blue print {bp_id} not found")
                return None
            return BluePrintInstance(
                bp_id=bp_po.bp_id,
                name=bp_po.name,
                description=bp_po.description,
                portal_node=bp_po.portal_node,
                action_nodes=bp_po.action_nodes,
                router_nodes=bp_po.router_nodes,
                connections=bp_po.connections,
            )

        except Exception as e:
            logger.exception(e)
            return None

    def __new__(cls, *args, **kwargs):
        if not hasattr(BluePrintManager, "_instance"):
            with BluePrintManager._instance_lock:
                if not hasattr(BluePrintManager, "_instance"):
                    BluePrintManager._instance = object.__new__(cls)
        return BluePrintManager._instance
