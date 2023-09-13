import logging
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
    # todo 校验action的有效性

    action_name: str
    queuing_time: int = 0
    action_script: str = None
    sharing_params: Dict = {}
    execute_result: Any = None

    def pre_loading(self, event: SceneEvent, **factor_value):
        if not self.action_script or self.action_script == '':
            return
        input_params = {
            'trigger_event': event,
            'execute_result': None,
            'sharing_params': self.sharing_params,
            **factor_value,
        }
        try:
            eval(self.action_script, input_params)
        except Exception as e:
            logger.exception(e)
            return False
        self.execute_result = input_params.get('execute_result', None)
