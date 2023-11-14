import logging
import threading
from typing import Dict, Type

from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from body.entity.function_call import FunctionDescribe

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
    """
    pass


class BaseActionMgr:
    """
    动作管理器，用于管理系统支持的动作
    """

    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            BaseActionMgr._ready = True
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
        if not hasattr(BaseActionMgr, "_instance"):
            with BaseActionMgr._instance_lock:
                if not hasattr(BaseActionMgr, "_instance"):
                    BaseActionMgr._instance = object.__new__(cls)
        return BaseActionMgr._instance