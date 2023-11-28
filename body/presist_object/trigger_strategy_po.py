import logging
from typing import Optional, List, Dict

from common_py.client.azure_mongo import MongoDBClient
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler
from pydantic import BaseModel

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

class AITriggerStrategyPo(BaseModel):
    # 策略ID
    strategy_id: str
    # 策略名称
    strategy_name: str
    # 触发动作，由哪个动作触发策略
    trigger_lst: List[str]
    # 策略优先级，同时命中的情况下，优先级高的生效 (0-500) 越小优先级越高
    strategy_priority: str
    # 策略生效时间
    start_time: str = None
    # 策略失效时间
    end_time: str = None
    # 策略在每个AI的生效次数 once/everyTime 暂不支持
    # self.frequency = kwargs.get('frequency', None)
    # 策略在每个AI实例的生效次数 int default 1, -1 means unlimited
    instance_frequency: str = '1'
    # 策略执行的概率(1, 100)
    possibility: str = '100'
    # 策略执行权重
    weight: Optional[str] = None

    action_type: str
    action_id: str


def load_all_AI_strategy_po() -> List[AITriggerStrategyPo]:
    strategy_po_lst = []
    mongodb_client = MongoDBClient()
    strategies = mongodb_client.find_from_collection("AI_trigger_strategy", filter={})
    if not strategies:
        return []
    for strategy in strategies:
        try:
            strategy_po_lst.append(AITriggerStrategyPo(**strategy))
        except Exception as e:
            logger.exception(e)
            continue
    return strategy_po_lst

