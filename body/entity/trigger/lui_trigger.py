import logging
import threading
from typing import List, Optional, Dict

from common_py.client.pg import query_vector_info
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from common_py.dto.lui_trigger import LUITrigger as LUITriggerDto, LUITriggerInfo
from body.entity.trigger.base_tirgger import BaseTrigger
from body.presist_object.trigger_po import load_all_trigger_po

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


def eval_lui_trigger(potential_triggers: List[str], target_text: str) -> Dict:
    results = query_vector_info(LUITriggerDto,
                                target_text,
                                meta_filter={'trigger_id': {'$in': potential_triggers}},
                                top_k=3,
                                threshold=0.80)
    results = [LUITriggerInfo(**item) for item in results]
    logger.info(f"eval_trigger: {[result.json() for result in results]}")
    trigger_id_map = {}
    for result in results:
        trigger_id_map[result.trigger_id] = True
    return trigger_id_map
