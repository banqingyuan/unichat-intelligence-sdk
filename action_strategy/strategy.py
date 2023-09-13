import logging
import random
import threading
import time

from common_py.model.scene import SceneEvent
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler
from memory_sdk.hippocampus import Hippocampus

from action_strategy.action import Action

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class AIActionStrategy:
    must_provide = ['strategy_id', 'strategy_name', 'strategy_priority', 'start_time', 'end_time', 'actions', 'trigger_actions', 'target']
    eval_result_execute = 'execute'
    eval_result_ignore = 'ignore'

    def __init__(self, **kwargs):
        # 策略ID
        self.strategy_id = kwargs.get('strategy_id')
        # 策略名称
        self.strategy_name = kwargs.get('strategy_name')
        # 策略优先级，同时命中的情况下，优先级高的生效 (0-500) 越小优先级越高
        self.strategy_priority = int(kwargs.get('strategy_priority'))
        # 策略生效时间
        self.start_time = int(kwargs.get('start_time'))
        # 策略失效时间
        self.end_time = int(kwargs.get('end_time'))
        # 策略在每个AI的生效次数 once/everyTime 暂不支持
        # self.frequency = kwargs.get('frequency', None)
        # 策略在每个AI实例的生效次数 int default 1, -1 means unlimited
        self._instance_frequency = int(kwargs.get('instance_frequency', 1))
        # 策略执行的概率(1, 100)
        self.possibility = int(kwargs.get('possibility', 100))
        # 策略生效的条件
        self.conditions = kwargs.get('conditions', None)
        # 满足条件后需要执行的动作
        actions = []
        action_list = kwargs.get('actions')
        for action_dict in action_list:
            actions.append(Action(**action_dict))
        self.actions = actions
        # 触发动作，比如，用户开启AI, 用户加入房间
        self.trigger_actions = kwargs.get('trigger_actions', None)
        # 目标类型， AI/User
        self.target_type = kwargs.get('target_type', None)
        # 进一步细化生效目标
        self.target_detail = kwargs.get('target_detail', None)
        self.thread_lock = threading.Lock()

        self._check_valid()

    def _check_valid(self):
        for key in self.must_provide:
            if getattr(self, key, None) is None:
                raise ValueError(f"invalid {key}")
        if not isinstance(self.actions, list):
            raise ValueError("actions must be list")
        if not isinstance(self.target_detail, list):
            raise ValueError("target_detail must be list")
        if not isinstance(self.trigger_actions, list):
            raise ValueError("trigger_actions must be list")

    def eval(self, trigger_event: SceneEvent, **factor_value):
        # 1. 检查trigger是否满足
        # 2. 检查condition是否满足
        if not self._check_effective():
            return self.eval_result_ignore
        if not self._check_trigger(trigger_event.event_name):
            return self.eval_result_ignore
        if not self._check_condition(trigger_event=trigger_event, condition_script=self.conditions, **factor_value):
            return self.eval_result_ignore
        if not self._hit_possibility():
            return self.eval_result_ignore
        return self.eval_result_execute

    def execute_count(self):
        try:
            self.thread_lock.acquire()
            if self._instance_frequency > 0:
                self._instance_frequency -= 1
                return True
            if self._instance_frequency == -1:
                return True
            return False
        finally:
            self.thread_lock.release()

    def _check_trigger(self, trigger_name: str):
        valid = False
        for trigger in [trigger for trigger in self.trigger_actions if trigger.name == trigger_name]:
            if trigger.get("type") == 'immediately':
                return True
        return valid

    def _check_effective(self):
        if time.time() < self.start_time or time.time() > self.end_time:
            return False
        if self._instance_frequency == 0:
            return False
        return True

    def _check_condition(self, trigger_event: SceneEvent, condition_script: str = '', **factor_value):
        if not condition_script:
            return True
        input_params = {
            'trigger_event': trigger_event,
            'hit': False,
            **factor_value,
        }
        try:
            eval(condition_script, input_params)
        except Exception as e:
            logger.exception(e)
            return False
        return input_params['hit']

    def _hit_possibility(self):
        if self.possibility == 100:
            return True
        return random.randint(1, 100) <= self.possibility


def build_strategy(strategy) -> AIActionStrategy:
    params = strategy
    return AIActionStrategy(**params)


if __name__ == '__main__':

    def check_condition(condition_script: str = '', **factor_value):
        if not condition_script:
            return True
        input_params = {
            **factor_value,
            'hit': False,
        }
        exec(condition_script, input_params)
        return input_params['hit']

    result = check_condition("if factor1  10: hit = True", factor1=15)
    print(result)  # 输出: True
