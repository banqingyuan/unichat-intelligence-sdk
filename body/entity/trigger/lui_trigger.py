import logging
import threading
from typing import List, Dict

from common_py.client.pg import query_vector_info
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from common_py.dto.lui_trigger import LUITrigger as LUITriggerDto, LUITriggerInfo
from body.entity.trigger.base_tirgger import BaseTrigger

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class LUITrigger(BaseTrigger):
    typ = 'LUI_trigger'
    trigger_name: str
    trigger_id: str
    trigger_corpus: List[str]



