import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import List, Dict, Optional

from common_py.ai_toolkit.openAI import filter_brackets, ChatGPTClient, Message, Model_gpt4, OpenAIChatResponse
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.chroma import ChromaCollection, ChromaDBManager, VectorRecordItem
from common_py.dto.ai_instance import AIBasicInformation
from common_py.dto.lui_trigger import LUITriggerInfo
from common_py.model.base import BaseEvent
from common_py.model.chat import ConversationEvent
from common_py.model.scene.scene import SceneEvent
from common_py.model.system_hint import SystemHintEvent
from common_py.utils.channel.util import get_AID_from_channel
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from body.blue_print.bp_instance import BluePrintInstance
from body.const import CollectionName_LUI
from body.entity.action_node import ActionNode
from body.entity.function_call import FunctionDescribe, Parameter, Properties
from body.entity.trigger.base_tirgger import BaseTrigger
from body.entity.trigger.lui_trigger import LUITrigger
from body.entity.trigger.scene_trigger import SceneTrigger
from body.entity.trigger.trigger_manager import TriggerMgr
from body.entity.trigger_strategy import AIActionStrategy, AIStrategyMgr
from memory_sdk.memory_manager import MemoryManager

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
        self.channel_name = kwargs.get('channel_name', None)
        self.ai_info: AIBasicInformation = kwargs.get('ai_info', None)
        self.action_queue: Queue = kwargs.get('action_queue', None)
        if not self.channel_name or not self.ai_info or not self.action_queue:
            raise Exception("AIStrategyManager init failed, channel_name or ai_info or action_queue is None")
        self.AID = get_AID_from_channel(self.channel_name)
        self.mongodb_client = MongoDBClient()

        # strategy_id -> strategy
        self.effective_strategy: Dict[str, AIActionStrategy] = {}

        # event_name -> trigger_id
        self.scene_event_name_to_trigger: Dict[str, List[SceneTrigger]] = {}

        # trigger_id to trigger
        self.trigger_map: Dict[str, BaseTrigger] = {}

        # trigger_id -> strategy  通常只有场景Trigger会对应多个策略
        self.trigger_strategy_mapping: Dict[str, List[AIActionStrategy]] = {}

        # All LUI trigger id
        self.LUI_trigger_lst: List[str] = []

        self.memory_mgr: MemoryManager = kwargs['memory_mgr']

        self.lui_collection: ChromaCollection = ChromaDBManager().get_collection(CollectionName_LUI)

    def load(self):
        if self.ai_info and self.ai_info.tpl_name:
            query_filter = {
                "$or": [
                    {
                        "AID": self.AID,
                    },
                    {
                        "tpl_name": {"$in": [self.ai_info.tpl_name]}
                    }
                ]
            }
        else:
            query_filter = {
                "AID": self.AID,
            }
        strategies_relation_info_lst = self.mongodb_client.find_from_collection("AI_strategy_relation", filter=query_filter)
        if len(strategies_relation_info_lst) == 0:
            logger.warning(f"AI {self.AID} don't have any strategy")
            return
        all_strategy_ids = {}
        for strategies_relation_info in strategies_relation_info_lst:
            if 'strategy_packages' in strategies_relation_info:
                strategy_package_ids = strategies_relation_info['strategy_packages']
                strategy_package_info = self.mongodb_client.find_from_collection("AI_strategy_package", filter={
                    "strategy_package_id": {"$in": strategy_package_ids}
                })
                strategy_id_list = strategy_package_info['strategy_list']
                for strategy_id in strategy_id_list:
                    # 放map里去重
                    all_strategy_ids[strategy_id] = True
            if 'strategy_list' in strategies_relation_info:
                strategy_id_list = strategies_relation_info['strategy_list']
                for strategy_id in strategy_id_list:
                    # 放map里去重
                    all_strategy_ids[strategy_id] = True

        all_strategy_id_lst = [strategy_id for strategy_id in all_strategy_ids.keys()]
        all_strategy_info = AIStrategyMgr().get_strategy_by_ids(
            all_strategy_id_lst,
            channel_name=self.channel_name,
            action_queue=self.action_queue,
            memory_mgr=self.memory_mgr
        )

        for strategy in all_strategy_info:
            self.effective_strategy[strategy.strategy_id] = strategy
        for _id, s in self.effective_strategy.items():
            self.bind_trigger(s)

    def bind_trigger(self, effective_strategy):
        lui_trigger_map = {}
        for trigger_id in effective_strategy.trigger_lst:
            trigger = TriggerMgr().get_trigger_by_id(trigger_id)
            if not trigger:
                logger.error(f"Trigger {trigger_id} not found")
                continue

            self.trigger_map[trigger_id] = trigger

            if trigger_id not in self.trigger_strategy_mapping:
                self.trigger_strategy_mapping[trigger_id] = []
            self.trigger_strategy_mapping[trigger_id].append(effective_strategy)

            if isinstance(trigger, LUITrigger):
                lui_trigger_map[trigger_id] = trigger

            if isinstance(trigger, SceneTrigger):
                if trigger.event_name not in self.scene_event_name_to_trigger:
                    self.scene_event_name_to_trigger[trigger.event_name] = []
                self.scene_event_name_to_trigger[trigger.event_name].append(trigger)

        self.LUI_trigger_lst.extend(list(lui_trigger_map.keys()))

    def unbundle_trigger(self, effective_strategy):
        for trigger_id in effective_strategy.trigger_lst:
            if trigger_id in self.trigger_strategy_mapping:
                self.trigger_strategy_mapping[trigger_id].remove(effective_strategy)
                if len(self.trigger_strategy_mapping[trigger_id]) == 0:
                    # 此时这个trigger下不再绑定任何策略, 需要解绑Trigger
                    del self.trigger_strategy_mapping[trigger_id]
                    trigger = self.trigger_map[trigger_id]

                    if isinstance(trigger, LUITrigger):
                        if trigger_id in self.LUI_trigger_lst:
                            self.LUI_trigger_lst.remove(trigger_id)
                    elif isinstance(trigger, SceneTrigger):
                        if trigger.event_name in self.scene_event_name_to_trigger:
                            self.scene_event_name_to_trigger[trigger.event_name].remove(trigger)

                    del self.trigger_map[trigger_id]
                    # todo 上报给事件监听中心，取消trigger事件

    def receive_scene_event(self, trigger_event: SceneEvent) -> Optional[BluePrintInstance]:

        eval_trigger = self.scene_event_name_to_trigger.get(trigger_event.event_name, [])
        eval_strategy = []
        if len(eval_trigger) == 0:
            return
        if len(eval_trigger) > 2:
            tasks = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                for trigger in eval_trigger:
                    tasks.append((trigger.trigger_id, executor.submit(trigger.eval_trigger, trigger_event)))
            for task in tasks:
                if task[1].result():
                    eval_strategy.extend(self.trigger_strategy_mapping[task[0]])
        else:
            for trigger in eval_trigger:
                if trigger.eval_trigger(trigger_event):
                    eval_strategy.extend(self.trigger_strategy_mapping[trigger.trigger_id])

        executable_lst = []

        max_priority: Optional[int] = None  # 最高优先级，数值上最小的那个
        for strategy in eval_strategy:
            eval_result = strategy.eval()
            if eval_result == AIActionStrategy.eval_result_execute:
                executable_lst.append(strategy)  # eval 得出了满足条件的策略，但是这并不意味这该策略一定会被执行
                max_priority = strategy.strategy_priority if max_priority is None or strategy.strategy_priority < max_priority else max_priority
            elif eval_result == AIActionStrategy.eval_result_remove:
                # 策略可能因为过期等原因不需要再执行了
                self.unbundle_trigger(strategy)
        logger.info(
            f"AI {self.AID} receive event {trigger_event.event_name}, executable strategy {[s.strategy_name for s in executable_lst]}")

        # 选择最高优先级的策略
        chosen_strategy = [s for s in executable_lst if s.strategy_priority == max_priority]

        weight_strategy_lst = [s for s in chosen_strategy if s.weight is not None]
        # 没有权重表示一定会执行
        winner_strategy_lst = [s for s in chosen_strategy if s.weight is None]
        if len(weight_strategy_lst) > 0:
            weight_lst = [s.weight for s in weight_strategy_lst]
            winner_strategy_lst.append(random.choices(weight_strategy_lst, weights=weight_lst, k=1)[0])

        blue_print_instance = None
        for s in winner_strategy_lst:
            blue_print_instance = self.activate_strategy(s.strategy_id, trigger_event)
        return blue_print_instance

    def activate_strategy(self, strategy_id: str, trigger_event: BaseEvent, **params) -> Optional[BluePrintInstance]:
        strategy = self.effective_strategy.get(strategy_id, None)
        if not strategy:
            logger.error(f"Strategy {strategy_id} not found")
            return None
        if not strategy.execute_count():
            self.unbundle_trigger(strategy)
        execute_action = strategy.get_action()
        execute_action.set_params(**params)

        if not execute_action:
            logger.error(f"Strategy {strategy_id} execute error cause by action not found")
            return None

        if isinstance(execute_action, BluePrintInstance):
            return execute_action

        if isinstance(execute_action, ActionNode):
            self.action_queue.put((execute_action, trigger_event))
            return None

    def receive_conversation_event(self,
                                   trigger_events: List[ConversationEvent],
                                   current_event: BaseEvent) -> (bool, SystemHintEvent, Optional[BluePrintInstance]):
        # 此处应该根据候选trigger_ids, 找到对应的action入参，拼成function describe，然后调用LLM
        # LUI触发的依据是意图的吻合程度，因此没有优先级之分
        tasks = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            for event in trigger_events:
                message_input = filter_brackets(event.message)
                message_splited = re.split(r'[;.,?!]', message_input)
                for message in message_splited:
                    tasks.append(executor.submit(self.eval_lui_trigger, self.LUI_trigger_lst, message))
        active_trigger_id_map = {}
        for task in tasks:
            triggered_lui_map = task.result()
            if triggered_lui_map:
                active_trigger_id_map.update(triggered_lui_map)

        potential_strategy_lst = []
        for trigger_id in active_trigger_id_map.keys():
            strategies = self.trigger_strategy_mapping.get(trigger_id, [])
            if len(strategies) == 0:
                logger.warning(f"trigger {trigger_id} don't have any strategy")
                continue
            if len(strategies) > 1:
                logger.warning(f"trigger {trigger_id} should not have more than one strategy")
            strategy = strategies[0]
            potential_strategy_lst.append(strategy)
        if len(potential_strategy_lst) == 0:
            return True, None, None
        describe_strategy_idx = {}
        func_describe_lst = []
        for strategy in potential_strategy_lst:
            func_describe = strategy.get_function_describe()
            describe_strategy_idx[func_describe['name']] = strategy.strategy_id
            if func_describe is not None:
                func_describe_lst.append(func_describe)

        func_describe = FunctionDescribe(
            name="InformationSupplement",
            description="If there is a suitable function call but the required parameter information is incomplete, "
                        "please call this function",
            parameters=Parameter(
                type='object',
                properties={
                    "information_to_be_added": Properties(
                        type='string',
                        description="Describe the information to be add"
                    )
                },
                required=['information_to_be_added']
            )
        )
        func_describe_lst.append(func_describe.gen_function_call_describe())

        chat_client = ChatGPTClient()
        messages = []
        message = Message(role='system',
                          content='''You should choose the appropriate function call based on the 
        contextual information provided; in principle, always use function call, and if there is no appropriate 
        function, output "no appropriate function call".Don't make assumptions about what values to plug into functions.
        If the required parameters are not complete, InformationSupplement should be called''')
        messages.append(message)
        messages.extend([m.get_message_from_event() for m in trigger_events])

        res = chat_client.generate(
            messages=messages,
            presence_penalty=0,
            frequency_penalty=0,
            functions=func_describe_lst,
            UUID=current_event.UUID,
            model_source=Model_gpt4,
            timeout=13,  # 经过统计数据，p99是11s
        )
        if isinstance(res, OpenAIChatResponse):
            function_name = res.function_name
            if not function_name:
                return True, None, None
            args = res.arguments
            if function_name == 'InformationSupplement':
                if len(args) > 0 and 'information_to_be_added' in args:
                    return True, Message(role='system', content=f'More information required. {args}')
                return True, None, None
            strategy_id = describe_strategy_idx.get(function_name, None)
            if not strategy_id:
                logger.error(f"The lui called can not match strategy_id, function name: {function_name}")
            blue_print = self.activate_strategy(strategy_id, current_event, **args)
            # todo 判断策略是否过期和策略执行计数+unbind
            if blue_print is not None:
                return False, None, blue_print
            return False, None, None
        return True, None, None

    def eval_lui_trigger(self, potential_triggers: List[str], target_text: str) -> Dict:
        try:
            vdb_res: List[VectorRecordItem] = self.lui_collection.query(
                input_data=target_text,
                top_k=3,
                meta_filter={'trigger_id': {'$in': potential_triggers}},
                threshold=0.70
            )
            results = [LUITriggerInfo(
                id=item.id,
                trigger_name=item.meta['trigger_name'],
                trigger_id=item.meta['trigger_id'],
                corpus_text=str(item.documents)
            ) for item in vdb_res]
            logger.info(f"eval_trigger: {[result.json() for result in results]}")
            trigger_id_map = {}
            for result in results:
                trigger_id_map[result.trigger_id] = True
            return trigger_id_map
        except Exception as e:
            logger.exception(e)
            return {}