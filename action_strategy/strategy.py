import random
import threading
import time


class AIActionStrategy:
    must_provide = ['strategy_id', 'strategy_name', 'strategy_priority', 'start_time', 'end_time', 'frequency', 'actions', 'trigger_actions', 'target_type', 'target_detail']
    eval_result_execute = 'execute'
    eval_result_ignore = 'ignore'

    def __init__(self, **kwargs):
        # 策略ID
        self.strategy_id = kwargs.get('strategy_id', None)
        # 策略名称
        self.strategy_name = kwargs.get('strategy_name', None)
        # 策略优先级，同时命中的情况下，优先级高的生效 (0-500) 越小优先级越高
        self.strategy_priority = kwargs.get('strategy_priority', None)
        # 策略生效时间
        self.start_time = kwargs.get('start_time', None)
        # 策略失效时间
        self.end_time = kwargs.get('end_time', None)
        # 策略在每个AI的生效次数 once/everyTime
        self.frequency = kwargs.get('frequency', None)
        # 策略在每个AI实例的生效次数 int default 1, -1 means unlimited
        self.instance_frequency = kwargs.get('instance_frequency', 1)
        # 策略执行的概率(1, 100)
        self.possibility = kwargs.get('possibility', 100)
        # 满足条件后需要执行的动作
        self.actions = kwargs.get('actions', None)
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

    def eval(self, trigger_name: str):
        # 1. 检查trigger是否满足
        # 2. 检查condition是否满足
        if not self._check_effective():
            return self.eval_result_ignore
        if not self._check_trigger(trigger_name):
            return self.eval_result_ignore
        if not self._check_condition():
            return self.eval_result_ignore
        if not self._hit_possibility():
            return self.eval_result_ignore
        return self.eval_result_execute

    def execute_count(self):
        try:
            self.thread_lock.acquire()
            if self.instance_frequency > 0:
                self.instance_frequency -= 1
                return True
            if self.instance_frequency == -1:
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
        if self.instance_frequency == 0:
            return False
        return True

    def _check_condition(self):
        return True

    def _hit_possibility(self):
        if self.possibility == 100:
            return True
        return random.randint(1, 100) <= self.possibility


def build_strategy(strategy) -> AIActionStrategy:
    params = strategy
    return AIActionStrategy(**params)


