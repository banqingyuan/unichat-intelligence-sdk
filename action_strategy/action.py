import logging
import time
from typing import Any, Dict

from common_py.model.scene import SceneEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from pydantic import BaseModel

Action_AI_Talking = 'AI_talking'

valid_action_lst = [Action_AI_Talking]

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class Action(BaseModel):
    """
    todo 校验action的有效性
    todo 有效action可枚举，登记使用方法
    Action 是用于执行场景触发的动作，也包括未来的蓝图动作
    action name是枚举值，由项目代码实现不同的action执行逻辑。
    每种action需要的参数种类是固定的，在sharing_params中提供
    参数生成逻辑不一而足，统一在action_script中把必要参数填充进sharing_params
    """

    action_name: str
    action_script: str
    queuing_time: int = 0
    active_time: int = 0
    sharing_params: Dict = {}

    def pre_loading(self, event: SceneEvent, **factor_value) -> bool:
        if not self.action_script or self.action_script == '':
            return False
        input_params = {
            'trigger_event': event,
            'sharing_params': self.sharing_params,
            **factor_value,
        }
        try:
            eval(self.action_script, input_params)
        except Exception as e:
            logger.exception(e)
            return False
        self.active_time = int(time.time())
        return True
