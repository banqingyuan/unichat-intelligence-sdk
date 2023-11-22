import logging
import threading
from typing import Dict, Optional

from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from body.entity.trigger.base_tirgger import BaseTrigger
from body.entity.trigger.lui_trigger import LUITrigger
from body.entity.trigger.scene_trigger import SceneTrigger
from body.presist_object.trigger_po import load_all_trigger_po

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class TriggerMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            TriggerMgr._ready = True
            self.scene_triggers_po_lst = []
            self.LUI_triggers_po_lst = []
            self.triggers: Dict[str, BaseTrigger] = {}
            self.refresh()

    def _refresh_trigger_po(self):
        self.scene_triggers_po_lst, self.LUI_triggers_po_lst = load_all_trigger_po()

    def _refresh_trigger(self):
        for trigger_po in self.LUI_triggers_po_lst:
            self.triggers[trigger_po.trigger_id] = LUITrigger(
                trigger_id=trigger_po.trigger_id,
                trigger_name=trigger_po.trigger_name,
                trigger_corpus=trigger_po.trigger_corpus
            )
        for trigger_po in self.scene_triggers_po_lst:
            self.triggers[trigger_po.trigger_id] = SceneTrigger(
                trigger_id=trigger_po.trigger_id,
                trigger_name=trigger_po.trigger_name
            )

    def refresh(self):
        # refresh every 2 minutes
        try:
            self._refresh_trigger_po()
            self._refresh_trigger()
        except Exception as e:
            logger.exception(e)
        threading.Timer(120, self.refresh).start()

    def get_trigger_by_id(self, trigger_id: str) -> Optional[BaseTrigger]:
        return self.triggers.get(trigger_id, None)

    def __new__(cls, *args, **kwargs):
        if not hasattr(TriggerMgr, "_instance"):
            with TriggerMgr._instance_lock:
                if not hasattr(TriggerMgr, "_instance"):
                    TriggerMgr._instance = object.__new__(cls)
        return TriggerMgr._instance


def _build_scene_trigger(trigger: Dict) -> SceneTrigger:
    return SceneTrigger(
        trigger_id=trigger['trigger_id'],
        trigger_name=trigger['trigger_name']
    )


def _build_lui_trigger(trigger: Dict) -> LUITrigger:
    return LUITrigger(
        trigger_id=trigger['trigger_id'],
        trigger_name=trigger['trigger_name'],
        trigger_corpus=trigger['trigger_corpus']
    )