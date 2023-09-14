import logging
from queue import Queue
from typing import List, Dict, Optional

from common_py.client.azure_mongo import MongoDBClient
from common_py.dto.ai_instance import AIBasicInformation
from common_py.model.scene import SceneEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from action_strategy.strategy import AIActionStrategy, build_strategy

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


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
        strategies = self.mongodb_client.find_from_collection("AI_action_strategy", filter={
            "$or": [
                {
                    "target.type": "AI",
                    "target.AI_type": self.ai_info.type,
                },
                {
                    "target.tpl_name": self.ai_info.tpl_name
                }
            ]
            # todo 补充筛选条件，现在暂不满足
        })
        for strategy in strategies:
            s = build_strategy(strategy)
            if s is not None:
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

    def receive_event(self, trigger_event: SceneEvent, **factor_value):
        eval_strategy = self.strategy_trigger_map.get(trigger_event.event_name, [])
        executable_lst = []

        max_priority: Optional[int] = None  # 最高优先级，数值上最小的那个
        for strategy in eval_strategy:
            if strategy.eval(trigger_event, **factor_value) == AIActionStrategy.eval_result_execute:
                executable_lst.append(strategy)
                max_priority = strategy.strategy_priority if max_priority is None or strategy.strategy_priority < max_priority else max_priority
        for s in executable_lst:
            if s.strategy_priority == max_priority:
                for action in s.actions:
                    if action.pre_loading(trigger_event, **factor_value):
                        self.action_queue.put(action)
            if not s.execute_count():
                self.effective_strategy.remove(s)
                eval_strategy.remove(s)
                self.strategy_trigger_map[trigger_event.event_name] = eval_strategy
                # todo 上报给事件监听中心，取消trigger事件
