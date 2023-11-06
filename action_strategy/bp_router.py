import logging
import uuid
from typing import Dict, Optional, List
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

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
    UUID: str = str(uuid.uuid4())

    llm_router: Optional[Dict] = None
    script_router: Optional[str] = None
    child_node: List[str] = []
