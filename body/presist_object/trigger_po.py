import logging
from typing import List, Dict

from common_py.client.azure_mongo import MongoDBClient
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from pydantic import BaseModel

from body.const import TriggerType_Scene, TriggerType_LUI

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class SceneTriggerPo(BaseModel):
    type = 'scene_trigger'
    trigger_id: str
    trigger_name: str


class LUITriggerPo(BaseModel):
    type = 'LUI_trigger'
    trigger_id: str
    trigger_name: str

    trigger_corpus: List[str]


def load_all_trigger_po() -> (List, List):
    mongodb_client = MongoDBClient()
    triggers = mongodb_client.find_from_collection("AI_triggers", filter={})
    if not triggers:
        return ([], [])

    scene_trigger_po_lst = []
    lui_trigger_po_lst = []
    for trigger in triggers:
        try:
            if trigger['type'] == TriggerType_Scene:
                scene_trigger_po_lst.append(_build_scene_trigger_po(trigger))
            elif trigger['type'] == TriggerType_LUI:
                lui_trigger_po_lst.append(LUITriggerPo(**trigger))
            else:
                logger.error(f"Unknown trigger type: {trigger['type']}")
        except Exception as e:
            logger.exception(e)
    return scene_trigger_po_lst, lui_trigger_po_lst


def _build_scene_trigger_po(trigger: Dict) -> SceneTriggerPo:
    return SceneTriggerPo(
        trigger_id=trigger['trigger_id'],
        trigger_name=trigger['trigger_name']
    )


def _build_lui_trigger_po(trigger: Dict) -> LUITriggerPo:
    return LUITriggerPo(
        trigger_id=trigger['trigger_id'],
        trigger_name=trigger['trigger_name'],
        trigger_corpus=trigger['trigger_corpus']
    )