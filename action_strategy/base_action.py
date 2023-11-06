import logging
import queue
import threading
from typing import Any, Dict, List, ClassVar, Optional, Type

import uuid
from common_py.model.system_hint import SystemHintEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from opencensus.trace import execution_context
from pydantic import BaseModel, Field

from action_strategy.function_call import FunctionDescribe

Action_AI_Talking = 'AI_talking'

valid_action_lst = [Action_AI_Talking]

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class BaseAction(FunctionDescribe):
    """
    todo 校验action的有效性
    todo 有效action可枚举，登记使用方法
    Action 是用于执行场景触发的动作，也包括未来的蓝图动作, 可以由LUI FunctionCall直接调用
    action name是枚举值，由项目代码实现不同的action执行逻辑。
    每种action需要的参数种类是固定的，在sharing_params中提供
    参数生成逻辑不一而足，统一在action_script中把必要参数填充进sharing_params
    params:
    active_time: int action的激活时间
    queuing_time: int 生效后到执行前的等待时间，如果允许执行时已经过了生效时效，就不再执行该动作。
    因为action_queue的block时间是3s，所以默认三秒重试一次，除非有其他动作生效，触发了所有待执行action的重试行为。
    system_hint: 特殊逻辑，如果有，动作执行时就会伴随语音输出.
    """

    queuing_time: int = 1
    active_time: int = 0
    system_hint: Optional[SystemHintEvent] = None
    params: dict = {}
    UUID: str = str(uuid.uuid4())

    def set_args(self, **kwargs):
        for name, prop in self.parameters.properties.items():
            if name in kwargs:
                v = None
                if prop.type == 'integer':
                    v = int(kwargs[name])
                elif prop.type == 'string':
                    v = str(kwargs[name])
                prop.value = v
                del kwargs[name]
        self.params = kwargs


class BpActionNode(FunctionDescribe):
    """
    蓝图动作节点，用于执行蓝图动作
    用于原子动作的组合编排
    """
    next_node_name: str

    tracer_header: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        action_params = {}
        system_message = kwargs.get('system_message', None)
        if system_message:
            action_params.update({'system_hint': SystemHintEvent(message=system_message)})
        if kwargs.get('queuing_time', None):
            action_params.update({'queuing_time': kwargs['queuing_time']})
        self.action: BaseAction = BpActionMgr().action_factory(self.name, **action_params)

    def set_tracer(self):
        tracer = execution_context.get_opencensus_tracer()
        self.tracer_header = tracer.propagator.to_headers(span_context=tracer.span_context)


class BpActionMgr:
    """
    蓝图动作管理器，用于管理蓝图动作
    """

    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            BpActionMgr._ready = True
            self.hippocampus: Dict[str, BpActionMgr] = {}
        self.action_collection: Dict[str, Type[BaseAction]] = {}

    def register_action(self, action: Type[BaseAction]):
        self.action_collection[action.name] = action

    def action_factory(self, action_name: str, **kwargs) -> BaseAction:
        try:
            action_class = self.action_collection[action_name]
            return action_class(**kwargs)
        except KeyError as e:
            logger.error(f"Missing key in blue print script: {e}")

    def __new__(cls, *args, **kwargs):
        if not hasattr(BpActionMgr, "_instance"):
            with BpActionMgr._instance_lock:
                if not hasattr(BpActionMgr, "_instance"):
                    BpActionMgr._instance = object.__new__(cls)
        return BpActionMgr._instance