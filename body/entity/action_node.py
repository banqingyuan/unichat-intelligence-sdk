import logging
import threading
import uuid
from typing import Optional, Dict

from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from opencensus.trace import execution_context
from common_py.model.system_hint import SystemHintEvent, new_system_hint_event
from pydantic import BaseModel

from body.const import ActionType_Atom, ActionType_Program
from body.entity.action_program import ActionProgram, ActionAtom, ActionProgramMgr
from body.entity.function_call import Parameter, FunctionDescribe
from body.presist_object.action_node import load_all_action_node_po, ActionNodePo

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class ActionNode(FunctionDescribe):
    """
    蓝图动作节点，用于执行蓝图动作
    用于原子动作的组合编排
    """
    # 全局唯一
    id: str

    queuing_time: int = 1
    system_hint: str = None

    # action_program 以后是由无代码拖拽生成，类似scratch ActionType_Atom/ActionType_Program
    action_type: str = ''
    action_program: Optional[ActionProgram]
    action_Atom: Optional[ActionAtom]

    preset_args: Optional[Dict[str, str]] = None

    def __init__(self,  **kwargs):
        super().__init__(**kwargs)

        if self.action_type == ActionType_Atom:
            self.action_Atom = ActionProgramMgr().get_action_atom(kwargs['action_id'])
        elif self.action_type == ActionType_Program:
            self.action_program = ActionProgramMgr().get_action_program(kwargs['action_id'])
        if self.preset_args:
            self.set_params(**self.preset_args)

    def set_params(self, **params):
        if self.action_type == ActionType_Atom:
            self.action_Atom.set_params(**params)
        elif self.action_type == ActionType_Program:
            self.action_program.set_params(**params)

    def set_tracer(self):
        tracer = execution_context.get_opencensus_tracer()
        self.tracer_header = tracer.propagator.to_headers(span_context=tracer.span_context)

    def execute(self):
        if self.action_type == ActionType_Atom:
            yield self.action_Atom
        elif self.action_type == ActionType_Program:
            return self.action_program.execute()

    def gen_function_call_describe(self, **kwargs):
        if self.action_type == ActionType_Atom:
            return self.action_Atom.gen_function_call_describe(**kwargs)
        elif self.action_type == ActionType_Program:
            return self.action_program.gen_function_call_describe(**kwargs)


class ActionNodeMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            ActionNodeMgr._ready = True
            self.action_program_mgr = ActionProgramMgr()
            self.action_node_po_dict: Dict[str, ActionNodePo] = {}
            self.refresh()

    def get_action_node(self, node_id: str) -> Optional[ActionNode]:
        try:
            action_node_po = self.action_node_po_dict.get(node_id, None)
            if not action_node_po:
                logger.error(f'get_action_node failed: node_id: {node_id}')
                return None

            return ActionNode(
                id=action_node_po.node_id,
                action_type=action_node_po.action_type,
                action_id=action_node_po.action_id,
                name=action_node_po.node_name,
                description=action_node_po.description,
                queuing_time=int(action_node_po.queuing_time),
                system_hint=action_node_po.system_prompt,
                preset_args=action_node_po.preset_args
            )
        except Exception as e:
            logger.exception(e)
            return None

    def refresh(self):
        try:
            self.action_node_po_dict = load_all_action_node_po()
        except Exception as e:
            logger.exception(e)
        threading.Timer(120, self.refresh).start()

    def __new__(cls, *args, **kwargs):
        if not hasattr(ActionNodeMgr, "_instance"):
            with ActionNodeMgr._instance_lock:
                if not hasattr(ActionNodeMgr, "_instance"):
                    ActionNodeMgr._instance = object.__new__(cls)
        return ActionNodeMgr._instance
