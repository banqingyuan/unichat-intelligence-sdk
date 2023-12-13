import logging
import random
import threading
import time
from queue import Queue
from typing import Optional, Dict, List, Union, Any

from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler

from body.blue_print.bp_instance import BluePrintManager, BluePrintInstance
from body.const import StrategyActionType_BluePrint, StrategyActionType_Action
from body.entity.action_node import ActionNodeMgr, ActionNode
from body.presist_object.trigger_strategy_po import AITriggerStrategyPo, load_all_AI_strategy_po

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class AIActionStrategy:
    must_provide = ['strategy_id', 'strategy_name', 'strategy_priority', 'start_time', 'end_time']
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

        self.memory_mgr = kwargs['memory_mgr']

        # strategy中绑定的action可以是多个，但是要求function describe必须一样。
        # 因为strategy的func des 是根据action透传的，并提供给llm做function call的判断.
        # 在多个action的情况下，会默认提供字典中首个action的function call describe
        self.actions: Dict[str, Dict[str, Any]] = kwargs['actions']
        # self.action_instance_dict: Dict[str, Union[BluePrintInstance, ActionNode]] = {}

        self.thread_lock = threading.Lock()
        self._check_valid()

    def get_action(self) -> Union[None, ActionNode, BluePrintInstance]:
        try:
            if not self.actions:
                logger.error(f"invalid actions: {self.strategy_id}")
                return
            if len(self.actions) == 1:
                action_key = list(self.actions.keys())[0]
                return self._get_action_instance(action_key=action_key)
            else:
                action_keys = [action_key for action_key in self.actions.keys()]
                action_weight_lst = [int(action['weight']) for action in self.actions.values()]
                execute_action_key = random.choices(action_keys, weights=action_weight_lst, k=1)[0]
                return self._get_action_instance(action_key=execute_action_key)
        except Exception as e:
            logger.exception(e)
            return None

    # def _init_action_instance(self):
    #     for _, action_config in self.actions.items():
    #         action_id = action_config['action_id']
    #         action_instance = self._get_action_instance(**action_config)
    #         if action_instance:
    #             self.action_instance_dict[action_id] = action_instance

    def _get_action_instance(self, action_key: str) -> Union[None, ActionNode, BluePrintInstance]:
        # 满足条件后需要执行的动作
        # todo Action单独一张表 剧本：ActionScript 单独一张表，蓝图单独一张表，触发单独一张表
        # 这里是触发的结构，触发可以绑定ActionNode，也可以绑定蓝图，但是不可以直接绑定Action
        try:
            config = self.actions.get(action_key, None)
            if not config:
                logger.error(f"action config not found: {action_key}")
                return None
            action_id = config['action_id']
            if config['action_type'] == StrategyActionType_BluePrint:
                instance = BluePrintManager().get_instance(action_id,
                                                           channel_name=self.channel_name,
                                                           action_queue=self.action_queue,
                                                           memory_mgr=self.memory_mgr)
            elif config['action_type'] == StrategyActionType_Action:
                instance = ActionNodeMgr().get_action_node(action_id)
            else:
                logger.error(f"invalid action_type: {config['action_type']}")
                return None
            if not instance:
                logger.error(f"action instance not found: {action_id}")
                return None
            if 'preset_params' in config:
                instance.set_params(**config['preset_params'])
            return instance
        except Exception as e:
            logger.exception(e)
            return None

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

    def get_function_describe(self, **kwargs) -> Optional[Dict]:
        return self._init_func_describe(**kwargs)

    def _init_func_describe(self, **kwargs) -> Optional[Dict]:
        if len(self.actions) == 0:
            logger.error(f"invalid actions: {self.strategy_id} caused by empty actions")
            return None
        if len(self.actions) > 1:
            for action_key, config in self.actions.items():
                if 'use_for_function_describe' in config and config['use_for_function_describe']:
                    instance = self._get_action_instance(action_key=action_key)
                    if instance:
                        return instance.gen_function_call_describe(**kwargs)
        action_key = list(self.actions.keys())[0]
        instance = self._get_action_instance(action_key=action_key)
        if instance:
            return instance.gen_function_call_describe(**kwargs)
        return None

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
            actions=strategy_po.actions,
            memory_mgr=kwargs['memory_mgr'],
        )

    def __new__(cls, *args, **kwargs):
        if not hasattr(AIStrategyMgr, "_instance"):
            with AIStrategyMgr._instance_lock:
                if not hasattr(AIStrategyMgr, "_instance"):
                    AIStrategyMgr._instance = object.__new__(cls)
        return AIStrategyMgr._instance

# if __name__ == '__main__':
#     actions = {
#         "a": {
#             "weight": "1"
#         },
#         "b": {
#             "weight": "5"
#         },
#     }
#     action_id_lst = list(actions.keys())
#     action_weight_lst = [int(action['weight']) for action in actions.values()]
#     execute_action_id = random.choices(action_id_lst, weights=action_weight_lst, k=1)[0]
#     print (execute_action_id)
