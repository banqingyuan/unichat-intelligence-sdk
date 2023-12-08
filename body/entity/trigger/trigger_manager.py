import logging
import threading
import time
from typing import Dict, Optional, List

from common_py.client.azure_mongo import MongoDBClient
from common_py.client.chroma import ChromaDBManager
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from body.const import CollectionName_LUI
from body.entity.trigger.base_tirgger import BaseTrigger
from body.entity.trigger.lui_trigger import LUITrigger
from body.entity.trigger.scene_trigger import SceneTrigger
from body.presist_object.trigger_po import load_all_trigger_po, LUITriggerPo, SceneTriggerPo, save_LUITriggerPo_to_vdb
from utils import check_sum_md5

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
            self.vdb_collection = ChromaDBManager().get_collection(CollectionName_LUI)
            self.first_check = True
            self.scene_triggers_po_lst: List[SceneTriggerPo] = []
            self.LUI_triggers_po_lst: List[LUITriggerPo] = []
            self.triggers: Dict[str, BaseTrigger] = {}
            self.LUI_check_sum_dict: Dict[str, str] = {}
            self.refresh()

    def _refresh_trigger_po(self):
        self.scene_triggers_po_lst, self.LUI_triggers_po_lst = load_all_trigger_po()

    def _refresh_trigger(self):
        # 分别在第一次触发场景和增量更新场景中处理
        # 1. 更新LUI触发信息到vdb
        # 2. 更新LUI Trigger实例
        # 暂时不做删除逻辑

        if self.first_check:
            same, new_check_sum = self._check_sum()
            for lui_po in self.LUI_triggers_po_lst:
                if not same:
                    save_LUITriggerPo_to_vdb(lui_po, self.vdb_collection)
                self.triggers[lui_po.trigger_id] = LUITrigger(
                    trigger_id=lui_po.trigger_id,
                    trigger_name=lui_po.trigger_name,
                    trigger_corpus=lui_po.trigger_corpus
                )
            self.vdb_collection.update_collection_metadata({"check_sum": new_check_sum})
            self.first_check = False
        else:
            for trigger_po in self.LUI_triggers_po_lst:
                check_sum = self.LUI_check_sum_dict.get(trigger_po.trigger_id, None)
                new_po_check_sum = check_sum_md5(trigger_po.json())
                if not check_sum or check_sum != new_po_check_sum:
                    save_LUITriggerPo_to_vdb(trigger_po, self.vdb_collection)
                    self.LUI_check_sum_dict[trigger_po.trigger_id] = new_po_check_sum

                    check_sum_str = ''.join([check_sum for check_sum in self.LUI_check_sum_dict.values()])
                    total_check_sum = check_sum_md5(check_sum_str)
                    self.vdb_collection.update_collection_metadata({"check_sum": total_check_sum})

                    self.triggers[trigger_po.trigger_id] = LUITrigger(
                        trigger_id=trigger_po.trigger_id,
                        trigger_name=trigger_po.trigger_name,
                        trigger_corpus=trigger_po.trigger_corpus
                    )

        for trigger_po in self.scene_triggers_po_lst:
            self.triggers[trigger_po.trigger_id] = SceneTrigger(
                trigger_id=trigger_po.trigger_id,
                trigger_name=trigger_po.trigger_name,
                event_name=trigger_po.event_name,
                condition_script=trigger_po.condition_script
            )

    def refresh(self):
        # refresh every 2 minutes
        try:
            logger.info("Start to refresh trigger")
            self._refresh_trigger_po()
            self._refresh_trigger()

        except Exception as e:
            logger.exception(e)
        threading.Timer(120, self.refresh).start()

    def _check_sum(self) -> (bool, str):
        # 初始化所有LUI trigger 的校验和并判断是否需要更新本地vdb
        check_sum_raw_data = ""
        for lui_po in self.LUI_triggers_po_lst:
            po_str = lui_po.json()
            check_sum = check_sum_md5(po_str)
            check_sum_raw_data += check_sum
            self.LUI_check_sum_dict[lui_po.trigger_id] = check_sum
        # calculate md5
        total_check_sum = check_sum_md5(check_sum_raw_data)

        metadata = self.vdb_collection.get_collection_metadata()
        if metadata and 'check_sum' in metadata and metadata['check_sum'] == total_check_sum:
            logger.info("Trigger check sum is the same, no need to update")
            return True, total_check_sum
        else:
            logger.info("Trigger check sum is different, need to update")
            return False, total_check_sum

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
        trigger_name=trigger['trigger_name'],
        event_name=trigger['event_name'],
        condition_script=trigger['condition_script']
    )


def _build_lui_trigger(trigger: Dict) -> LUITrigger:
    return LUITrigger(
        trigger_id=trigger['trigger_id'],
        trigger_name=trigger['trigger_name'],
        trigger_corpus=trigger['trigger_corpus']
    )

if __name__ == '__main__':
    # pg_config = {
    #     "host": "c.postgre-east.postgres.database.azure.com",
    #     # "host": "c-unichat-postgres-prod.q2t5np375m754a.postgres.cosmos.azure.com",
    #     "user": "citus",
    #     "db_name": "citus"
    # }
    # PgEngine(**pg_config)
    MongoDBClient(DB_NAME="unichat-backend")
    TriggerMgr()
    # print(TriggerMgr().vdb_collection.get())
    print(TriggerMgr().vdb_collection.query('', {}, ))
    while True:
        time.sleep(1)

