import logging
import time
from typing import Any, Dict
from common_py.model.base import BaseEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from memory_sdk.event_block import load_block_from_mongo
from opencensus.trace import execution_context
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
    params:
    active_time: int 生效后到执行前的等待时间，如果允许执行时已经过了生效时效，就不再执行该动作。
    因为action_queue的block时间是3s，所以默认三秒重试一次，除非有其他动作生效，触发了所有待执行action的重试行为。
    """

    action_describe: str
    action_name: str
    action_script: str = ''
    queuing_time: int = 1
    active_time: int = 0
    sharing_params: Dict = {}
    next_node_name: str = None

    def pre_loading(self, trigger_event: BaseEvent, **factor_value) -> bool:
        if not self.action_script or self.action_script == '':
            return False
        input_params = {
            'trigger_event': trigger_event,
            'sharing_params': self.sharing_params,
            'tracer': execution_context.get_opencensus_tracer(),
            'load_block_from_mongo': load_block_from_mongo,
            **factor_value,
        }
        try:
            exec(self.action_script, input_params)
        except Exception as e:
            logger.exception(e)
            return False
        self.active_time = int(time.time())
        return True