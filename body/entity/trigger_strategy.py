import logging
import random
import threading
import time
from queue import Queue
from typing import Optional, Dict, List

from common_py.model.base import BaseEvent
from common_py.model.chat import ConversationEvent
from common_py.model.scene import SceneEvent
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler

from body.blue_print.bp_instance import BluePrintManager
from body.const import StrategyActionType_BluePrint, StrategyActionType_Action
from body.entity.action_node import ActionNodeMgr
from body.presist_object.trigger_strategy_po import AITriggerStrategyPo, load_all_AI_strategy_po

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class AIActionStrategy:
    must_provide = ['strategy_id', 'strategy_name', 'strategy_priority', 'start_time', 'end_time', 'trigger_actions']
    eval_result_execute = 'execute'
    eval_result_ignore = 'ignore'
    eval_result_remove = 'remove'

    def __init__(self, **kwargs):
        # 策略ID
        self.strategy_id = kwargs['strategy_id']
        # 策略名称
        self.strategy_name = kwargs['strategy_name']
        # 触发动作，比如，用户开启AI, 用户加入房间
        self.trigger_lst = kwargs['trigger_lst']
        # 策略优先级，同时命中的情况下，优先级高的生效 (0-500) 越小优先级越高
        self.strategy_priority = int(kwargs['strategy_priority'])
        # 策略生效时间
        self.start_time = int(kwargs['start_time']) if kwargs.get('start_time', None) else 0
        # 策略失效时间
        self.end_time = int(kwargs['end_time']) if kwargs.get('end_time', None) else 0
        # 策略在每个AI的生效次数 once/everyTime 暂不支持
        # self.frequency = kwargs.get('frequency', None)
        # 策略在每个AI实例的生效次数 int default 1, -1 means unlimited
        self.instance_frequency = int(kwargs['instance_frequency']) if kwargs.get('instance_frequency', None) else 1
        # 策略执行的概率(1, 100)
        self.possibility = int(kwargs['possibility']) if kwargs.get('possibility', None) else 100
        # 策略执行权重
        self.weight: Optional[int] = int(kwargs['weight']) if kwargs.get('weight', None) else None

        self.channel_name = kwargs['channel_name']
        self.action_queue: Queue = kwargs['action_queue']

        memory_mgr = kwargs['memory_mgr']

        # 满足条件后需要执行的动作
        # todo Action单独一张表 剧本：ActionScript 单独一张表，蓝图单独一张表，触发单独一张表
        # 这里是触发的结构，触发可以绑定ActionNode，也可以绑定蓝图，但是不可以直接绑定Action
        if kwargs['action_type'] == StrategyActionType_BluePrint:
            self.blue_print = BluePrintManager().get_instance(kwargs['action_id'],
                                                              channel_name=self.channel_name,
                                                              action_queue=self.action_queue,
                                                              memory_mgr=memory_mgr)
        elif kwargs['action_type'] == StrategyActionType_Action:
            self.action = ActionNodeMgr().get_action_node(kwargs['action_id'])
        else:
            raise ValueError(f"invalid action_type: {kwargs['action_type']}")
        self.thread_lock = threading.Lock()
        self._check_valid()

    def _check_valid(self):
        for key in self.must_provide:
            if getattr(self, key, None) is None:
                raise ValueError(f"invalid {key}")
        if not isinstance(self.trigger_lst, list):
            raise ValueError("trigger_actions must be list")

    def eval(self):
        try:
            if not self._check_effective():
                return self.eval_result_remove
            if not self._hit_possibility():
                return self.eval_result_ignore
            return self.eval_result_execute
        except Exception as e:
            logger.exception(e)
            return self.eval_result_ignore

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

    def get_init_func_describe(self) -> Optional[Dict]:
        if self.action:
            return self.action.gen_function_call_describe()
        if self.blue_print:
            return self.blue_print.gen_function_call_describe()

    def _check_effective(self):
        if time.time() < self.start_time or time.time() > self.end_time:
            return False
        if self.instance_frequency == 0:
            return False
        return True

    def _hit_possibility(self):
        if self.possibility == 100:
            return True
        return random.randint(1, 100) <= self.possibility


class AIStrategyMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            AIStrategyMgr._ready = True
            self.strategy_po_map: Dict[str, AITriggerStrategyPo] = {}
            self.refresh()

    def _refresh_strategy_po(self):
        strategy_po_lst = load_all_AI_strategy_po()
        self.strategy_po_map = {strategy.strategy_id: strategy for strategy in strategy_po_lst}

    def refresh(self):
        # refresh every 2 minutes
        try:
            self._refresh_strategy_po()
        except Exception as e:
            logger.exception(e)
        threading.Timer(120, self.refresh).start()

    def get_strategy_by_ids(self, strategy_ids: list, **kwargs) -> List[AIActionStrategy]:
        strategy_lst = []
        for strategy_id in strategy_ids:
            strategy = self.get_strategy_by_id(strategy_id, **kwargs)
            if strategy:
                strategy_lst.append(strategy)
        return strategy_lst


    def get_strategy_by_id(self, strategy_id: str, **kwargs) -> Optional[AIActionStrategy]:
        strategy_po = self.strategy_po_map.get(strategy_id, None)
        if not strategy_po:
            logger.error(f"strategy_po not found: {strategy_id}")
            return None
        return AIActionStrategy(
            strategy_id=strategy_po.strategy_id,
            strategy_name=strategy_po.strategy_name,
            trigger_lst=strategy_po.trigger_lst,
            strategy_priority=strategy_po.strategy_priority,
            start_time=strategy_po.start_time,
            end_time=strategy_po.end_time,
            instance_frequency=strategy_po.instance_frequency,
            possibility=strategy_po.possibility,
            weight=strategy_po.weight,
            channel_name=kwargs['channel_name'],
            action_queue=kwargs['action_queue'],
            action_type=strategy_po.action_type,
            action_id=strategy_po.action_id,
            memory_mgr=kwargs['memory_mgr'],
        )

    def __new__(cls, *args, **kwargs):
        if not hasattr(AIStrategyMgr, "_instance"):
            with AIStrategyMgr._instance_lock:
                if not hasattr(AIStrategyMgr, "_instance"):
                    AIStrategyMgr._instance = object.__new__(cls)
        return AIStrategyMgr._instance


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
