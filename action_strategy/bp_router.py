import logging
import time
from typing import Dict, Optional, List

from common_py.ai_toolkit.openAI import ChatGPTClient
from common_py.model.base import BaseEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from opencensus.trace import execution_context

from action_strategy.function_call import FunctionDescribe, Parameter

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class RouterNode(FunctionDescribe):
    """
    路由节点等待一个输入，这个输入应该是一个事件
    """

    name: str
    description: str
    parameters: Parameter = Parameter(type='object')

    llm_router: Optional[Dict] = None
    script_router: Optional[str] = None
    child_node: List[str] = []
