import logging
import queue
import threading
from typing import Dict, Optional, List, Union, Any
from common_py.ai_toolkit.openAI import ChatGPTClient, Message, OpenAIChatResponse, Model_gpt4
from common_py.dto.ai_instance import AIBasicInformation, InstanceMgr
from common_py.dto.user import UserBasicInformation, UserInfoMgr
from common_py.model.base import BaseEvent
from common_py.model.chat import ConversationEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from body import const
from body.blue_print.bp_router import RouterNode, BPRouterManager
from body.const import BPNodeType_Action, BPNodeType_Router
from body.entity.action_node import ActionNode, ActionNodeMgr
from body.entity.function_call import FunctionDescribe, Parameter
from body.funcs import Funcs
from body.presist_object.bp_instance_po import load_all_bp_po, BluePrintPo
from memory_sdk.hippocampus import Hippocampus, HippocampusMgr
from memory_sdk.memory_entity import UserMemoryEntity
from memory_sdk.memory_manager import MemoryManager

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

BluePrintResult_Ignore = 'ignore'  # 本次不执行蓝图
BluePrintResult_Executed = 'executed'  # 本次已成功执行蓝图
BluePrintResult_Finished = 'finished'  # 蓝图已执行完毕
BluePrintResult_SelfKill = 'self_kill'  # 蓝图出错，不再执行

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

    self_cancel_limit = 5

    def __init__(self, **kwargs):
        try:
            self.bp_id = kwargs['bp_id']
            self.name = kwargs['name']
            self.description = kwargs['description']

            self.unactive_time_count = 0

            # eg. {'上游节点id', {'下游节点id', {'上游出参': '下游入参'}}}
            self.connection_mapping: Dict[str, Dict[str, Dict[str, str]]] = kwargs['connections']

            # self._construct_blue_print(kwargs)
            self.nodes_dict: Dict[str, Dict[str, Any]] = kwargs['nodes_dict']
            self.node_instance_dict: Dict[str, Union[RouterNode, ActionNode]] = {}

            portal_node_instance = self._get_node_instance(kwargs['portal_node'])
            if not portal_node_instance:
                raise Exception("Portal node not found")
            self.portal_node_name = kwargs['portal_node']
            self.current_node_name = kwargs['portal_node']

            self.action_queue: Optional[queue.Queue] = kwargs['action_queue']
            self.llm_client = ChatGPTClient(temperature=0.6)
            self.memory_mgr: MemoryManager = kwargs['memory_mgr']
            self.channel_name: str = ''
        except KeyError as e:
            logger.error(f"Missing key in blue print script: {e}")
            raise Exception("Missing key in blue print script")

    # def _construct_blue_print(self, bp_po: Dict):
    #     """
    #     只能存在一个节点被设置为入口
    #     动作节点至多有一个出度，且出度只能指向路由节点
    #     路由节点至少有一个出度
    #     """
    #     for node_name, node in self.nodes_dict.items():
    #         if node['type'] == BPNodeType_Router:
    #             self.nodes_typ_idx[node_name] = BPNodeType_Router
    #         elif node['type'] == BPNodeType_Action:
    #             self.nodes_typ_idx[node_name] = BPNodeType_Action

    def start_bp(self, event: BaseEvent) -> (str, Optional[list]):
        return self._execute(event)

    def execute(self, event: BaseEvent) -> (str, Optional[list]):
        current_node = self.node_instance_dict[self.current_node_name]
        if not isinstance(current_node, RouterNode):
            raise Exception("Current node is not router node")

        if current_node.script_router is not None:
            if isinstance(event, ConversationEvent):
                # script_router expect a SceneEvent
                self.unactive_time_count += 1
                if self.unactive_time_count > (self.self_cancel_limit + 1):
                    return BluePrintResult_SelfKill, None
                return self._collect_blue_print_fc_describe()
        else:
            # then it must be a llm router
            if not isinstance(event, ConversationEvent):
                return BluePrintResult_Ignore, None
        execute_status = self._execute(event)
        return execute_status, None

    def _collect_blue_print_fc_describe(self) -> (str, Optional[list]):
        cancel = FunctionDescribe(
            name='CancelCurrentBluePrintTask',
            description=f'Current blue print task is: {self.description} \n '
                        f'This function is called if the user directly indicates that they want to stop this task.',
        )
        return BluePrintResult_Ignore, [cancel.gen_function_call_describe()]

    def _execute(self, event: BaseEvent) -> str:
        try:
            node = self.node_instance_dict[self.current_node_name]
            if isinstance(node, RouterNode):
                next_node_name, params = self._execute_router(node, event)
                if next_node_name is None or next_node_name == '':
                    logger.error(f"Next node id is empty: {node.id}")
                    return BluePrintResult_SelfKill
                if next_node_name != node.id:
                    self.unactive_time_count = 0
                next_node = self._get_node_instance(next_node_name)
                if params:
                    next_node.set_params(**params)
                if isinstance(next_node, RouterNode):
                    self.current_node_name = next_node_name
                    return self._execute(event)
                elif isinstance(next_node, ActionNode):
                    # 在蓝图中进入Action节点，不需要前置判断
                    # if next_node.pre_loading(event):
                    self.action_queue.put((next_node, event))
                    next_router_node_name = self._get_child_node_of_action_node(next_node_name)
                    if not next_router_node_name:
                        return BluePrintResult_Finished
                    self.current_node_name = next_router_node_name
                    return BluePrintResult_Executed
            if isinstance(node, ActionNode):
                self.action_queue.put((node, event))
                next_node_name = self._get_child_node_of_action_node(self.current_node_name)
                if not next_node_name:
                    return ''
                self.current_node_name = next_node_name
                return BluePrintResult_Executed
        except Exception as e:
            # todo 退出蓝图
            logger.exception(e)
            return BluePrintResult_SelfKill

    def gen_function_call_describe(self, **kwargs) -> Optional[Dict]:
        # 入口是Router的话如何提供function call describe需要重新设计
        node = self.node_instance_dict[self.current_node_name]
        if isinstance(node, ActionNode):
            return node.gen_function_call_describe(**kwargs)
        fd = FunctionDescribe(
            name=self.name,
            description=self.description,
        )
        return fd.gen_function_call_describe(**kwargs)

    def set_params(self, **kwargs):
        node = self.node_instance_dict[self.portal_node_name]
        node.set_params(**kwargs)

    def _execute_router(self, node: RouterNode, trigger_event: BaseEvent) -> (str, Dict[str, str]):
        # 首先判断是否使用脚本路由，如果不使用，默认使用llm路由
        # 如果是conversation event, 暂不支持使用脚本路由
        if isinstance(trigger_event, ConversationEvent):
            return self._execute_llm_router(node, trigger_event)
        shared_conditions = ''
        if node.script_router and node.script_router != '':
            # script 既可以直接进行route操作，也可以作为llm的补充【通过设置shared_conditions来实现】
            next_node, shared_conditions, params = self._execute_router_script_node(node, trigger_event)
            if next_node != '':
                return next_node, params
            if shared_conditions == '':
                return '', None
        return self._execute_llm_router(node, trigger_event, shared_conditions)

    def _execute_router_script_node(self, node: RouterNode, event: BaseEvent) -> (str, str, Dict[str, str]):
        nodes_name = self._get_all_child_node_name(self.current_node_name)
        input_params = {
            'optional_child_node': nodes_name,
            'trigger_event': event,
            # 'tracer': execution_context.get_opencensus_tracer(),
            'next_node': None,
            'output_args_dict': {},
            'input_args_dict': node.get_all_values(),
            'shared_conditions': '',

            'user_info': None,
            'AI_info': None,
            'hippocampus': None,
            'AI_memory_of_user': None,
            'funcs': Funcs(),
        }

        UID = event.get_UID()
        if UID:
            user_info: UserBasicInformation = UserInfoMgr().get_instance_info(UID)
            input_params['user_info'] = user_info
        AID = event.AID
        if AID:
            AI_info: AIBasicInformation = InstanceMgr().get_instance_info(AID)
            input_params['AI_info'] = AI_info
        if UID and AID:
            hippocampus: Hippocampus = HippocampusMgr().get_hippocampus(AID)
            if hippocampus:
                input_params['hippocampus'] = hippocampus
                AI_memory_of_user: UserMemoryEntity = hippocampus.load_memory_of_user(UID)
                input_params['AI_memory_of_user'] = AI_memory_of_user
        try:
            exec(node.script_router, input_params)
        except Exception as e:
            logger.exception(e)
            return '', '', None

        if len(input_params['output_args_dict']) > 0:
            output_params = input_params['output_args_dict']
        else:
            output_params = None
        if input_params['next_node'] is None or input_params['next_node'] == '':
            logger.error(f"Next node name is empty: {self.current_node_name}")
            return '', input_params['shared_conditions'], output_params
        return input_params['next_node'], input_params['shared_conditions'], output_params

    def _execute_llm_router(self, router: RouterNode, trigger_event: BaseEvent, shared_conditions: str = None) -> (str, Dict[str, str]):
        mission_purpose = self.description
        known_conditions = ''
        for event in self.memory_mgr.get_event_list(BaseEvent, 6):
            known_conditions += event.description() + '\n'
        if shared_conditions:
            known_conditions += shared_conditions + '\n'
        child_nodes = self._get_all_child_node_name(self.current_node_name)
        if child_nodes is None or len(child_nodes) == 0:
            logger.error(f"Router node {router.id} has no child node")
            return '', None
        functions = []
        for child_node_name in child_nodes:
            node_instance = self._get_node_instance(child_node_name)

            def replace_function_name_in_function_call_describe():
                # function call 不能使用模板的function name，存在重复的可能性，需要使用蓝图中自定义的function name
                function_call_description = node_instance.gen_function_call_describe()
                function_call_description['name'] = child_node_name
                if 'description' in self.nodes_dict[child_node_name] and self.nodes_dict[child_node_name]['description'] != '':
                    function_call_description['description'] = self.nodes_dict[child_node_name]['description']
                return function_call_description

            functions.append(replace_function_name_in_function_call_describe())

        prompt = const.router_prompt.format(
            mission_purpose=mission_purpose,
            known_conditions=known_conditions,
        )

        for i in range(3):
            try:
                function_name, arguments = self._query_llm_and_get_function_call_resp(prompt, trigger_event, functions)
                return function_name, arguments
            except FunctionCallException as e:
                logger.warning(f"Function call failed: {e} try again")
                continue
        return None, None

    def _query_llm_and_get_function_call_resp(self, prompt: str, trigger_event: BaseEvent, functions: List[Dict]) -> (str, Dict[str, str]):
        resp = self.llm_client.generate(
            messages=[
                Message(role='system', content=prompt),
            ],
            UUID=trigger_event.UUID,
            functions=functions,
            model_source=Model_gpt4,
        )
        logger.info(f"_query_llm_and_get_function_call_resp llm response: {resp.json()}")
        if isinstance(resp, OpenAIChatResponse):
            if resp.function_name is not None and resp.function_name != '':
                # params 的引用持有不会影响到func的释放
                return resp.function_name, resp.arguments
            else:
                raise FunctionCallException(f"Function name is empty with response {resp.json()}")
        else:
            raise FunctionCallException(f"Function call failed with response {resp.json()}")

    def _get_child_node_of_action_node(self, node_name) -> Optional[str]:
        next_round_node_name = self._get_all_child_node_name(node_name)
        if len(next_round_node_name) == 0:
            return None
        elif len(next_round_node_name) > 1:
            logger.error(f"Action Node should not have more than one child node: {node_name}")
            return None
        next_round_node = self._get_node_instance(next_round_node_name[0])
        if not isinstance(next_round_node, RouterNode):
            logger.error(f"Next round node should be router node: {next_round_node_name}")
            return None
        return next_round_node_name[0]

    def _get_all_child_node_name(self, node_name: str) -> List[str]:
        nodes = []
        if node_name not in self.connection_mapping:
            return nodes
        child_node_names = self.connection_mapping[node_name].keys()
        for child_node_name in child_node_names:
            nodes.append(child_node_name)
        return nodes

    def _get_node_instance(self, node_name: str) -> Union[RouterNode, ActionNode]:
        node_info = self.nodes_dict.get(node_name, None)
        if not node_info:
            raise Exception(f"Node {node_name} not found")
        node_id = node_info['node_id']
        node_typ = node_info['node_type']
        if node_typ == BPNodeType_Action:
            node = ActionNodeMgr().get_action_node(node_id)
        elif node_typ == BPNodeType_Router:
            node = BPRouterManager().get_router(node_id)
        else:
            raise Exception("Unknown node type")
        self.node_instance_dict[node_name] = node
        if 'preset_args' in node_info and node_info['preset_args']:
            node.set_params(**node_info['preset_args'])
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

    def get_instance(self, bp_id: str, **context_info) -> Optional[BluePrintInstance]:
        try:
            bp_po = self.bp_po_dict.get(bp_id, None)
            if not bp_po:
                logger.error(f"blue print {bp_id} not found")
                return None
            channel_name = context_info.get('channel_name', None)
            llm_client = ChatGPTClient(temperature=0)
            action_queue = context_info['action_queue']
            memory_mgr = context_info['memory_mgr']
            if not channel_name or not action_queue:
                logger.error(f"channel_name or action_queue not found")
                return None
            return BluePrintInstance(
                bp_id=bp_po.bp_id,
                name=bp_po.bp_name,
                description=bp_po.description,
                portal_node=bp_po.portal_node,
                # action_nodes=bp_po.action_nodes,
                # router_nodes=bp_po.router_nodes,
                nodes_dict=bp_po.nodes_dict,
                connections=bp_po.connections,
                channel_name=channel_name,
                llm_client=llm_client,
                action_queue=action_queue,
                memory_mgr=memory_mgr,
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

'''
        input_params = {
            'optional_child_node': nodes,
            'trigger_event': event,
            'tracer': execution_context.get_opencensus_tracer(),
            'next_node': None,
            'output_args_dict': {},
            'shared_conditions': '',

            'user_info': None,
            'AI_info': None,
            'hippocampus': None,
            'AI_memory_of_user': None,
        }'''
def router_script_playground(
        optional_child_node: List[str],
        trigger_event: BaseEvent,
        next_node: str,
        output_args_dict: Dict[str, str],
        input_args_dict: Dict[str, str],
        shared_conditions: str,
        user_info: Optional[UserBasicInformation],
        AI_info: Optional[AIBasicInformation],
        hippocampus: Optional[Hippocampus],
        AI_memory_of_user: Optional[UserMemoryEntity],
):
    pass