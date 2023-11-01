import logging
import time
from typing import Dict, Optional, List

from common_py.ai_toolkit.openAI import ChatGPTClient
from common_py.model.base import BaseEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from opencensus.trace import execution_context

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

class RouterNode:
    """
    路由节点等待一个输入，这个输入应该是一个事件
    """

    def __init__(self, **kwargs):
        self.name: str = kwargs['name']
        self.description: str = kwargs['description']
        self.llm_router: Optional[Dict] = kwargs.get('llm_router', None)
        self.script_router: str = kwargs.get('script_router', None) # todo 考虑把脚本迁移到仓库里
        self.child_node: List[str] = kwargs.get('child_node', [])








