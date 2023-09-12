from queue import Queue
from typing import List, Dict, Optional

from common_py.client.azure_mongo import MongoDBClient
from common_py.dto.ai_instance import AIBasicInformation

from action_strategy.strategy import AIActionStrategy, build_strategy


def build_action(action):
    pass


def build_condition(condition):
    pass


class AIStrategyManager:
    def __init__(self, **kwargs):
        self.AID = kwargs.get('AID', None)
        self.ai_info: AIBasicInformation = kwargs.get('ai_info', None)
        self.action_queue: Queue = kwargs.get('action_queue', None)
        if not self.AID or not self.ai_info or not self.action_queue:
            raise Exception("AIStrategyManager init failed, AID or ai_info or action_queue is None")
        self.mongodb_client = MongoDBClient()
        self.effective_strategy: List[AIActionStrategy] = []
        self.strategy_trigger_map: Dict[str, List[AIActionStrategy]] = {}

    def load(self):
        strategies = self.mongodb_client.find_from_collection("ai_action_strategy", filter={
            "$or": [
                {
                    "target_detail.all": True
                },
                {
                    "target_type": "AI",
                    # "target_detail.role": "$role",
                    # "target_detail.close_level": "$provided_close_level"
                    # todo 补充筛选条件，现在暂不满足
                }
            ]
        })
        for strategy in strategies:
            if s := build_strategy(strategy) is not None:
                self.effective_strategy.append(s)
        for s in self.effective_strategy:
            for trigger in s.trigger_actions:
                trigger_name = trigger.get("name", None)
                self.strategy_trigger_map.setdefault(trigger_name, []).append(s)

    def bind_trigger(self, effective_strategy):
        # todo 上报给事件监听中心， 注册trigger事件
        # for s in self.effective_strategy:
        #     for trigger_action in s.trigger_actions:
        #         trigger_action
        pass

    def receive_event(self, trigger_event: str, **factor_value):
        eval_strategy = self.strategy_trigger_map.get(trigger_event, [])
        executable_lst = []

        max_priority: Optional[int] = None  # 最高优先级，数值上最小的那个
        for strategy in eval_strategy:
            if strategy.eval(trigger_event, **factor_value):
                executable_lst.append(strategy)
                max_priority = strategy.strategy_priority if max_priority is None or strategy.strategy_priority < max_priority else max_priority
        for s in executable_lst:
            if s.strategy_priority == max_priority:
                for action in s.actions:
                    # todo 校验action的有效性
                    self.action_queue.put(action)
            if not s.execute_count():
                self.effective_strategy.remove(s)
                eval_strategy.remove(s)
                self.strategy_trigger_map[trigger_event] = eval_strategy
                # todo 上报给事件监听中心，取消trigger事件
