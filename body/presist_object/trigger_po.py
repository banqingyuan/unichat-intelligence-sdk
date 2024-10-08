import logging
import uuid
from typing import List, Dict, Optional
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.chroma import ChromaCollection, VectorRecordItem
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
    event_name: str
    condition_script: str = None


class LUITriggerPo(BaseModel):
    type = 'LUI_trigger'
    trigger_id: str
    trigger_name: str
    trigger_corpus: List[str]


def save_LUITriggerPo_to_vdb(po: LUITriggerPo, collection: ChromaCollection):
    collection.delete(where={'trigger_id': po.trigger_id})
    vector_records = []
    for corpus_text in po.trigger_corpus:
        vector_records.append(VectorRecordItem(
            id=str(uuid.uuid4()),
            meta={
                "trigger_id": po.trigger_id,
                "trigger_name": po.trigger_name,
            },
            documents=corpus_text
        ))
    collection.upsert_many(vector_records)
    logger.info(f"Save LUI trigger to vdb: {po.trigger_name}")

    # with ThreadPoolExecutor(max_workers=5) as executor:
    #     for corpus_text in po.trigger_corpus:
    #         task = executor.submit(
    #             **{
    #                 "id": str(uuid.uuid4()),
    #                 "trigger_name": self.trigger_name,
    #                 "trigger_id": self.trigger_id,
    #                 "corpus_text": corpus_text
    #             }
    #         )
    #         tasks.append(task)
    # for task in tasks:
    #     lui = task.result()
    #     if lui:
    #         lui_lst.append(lui)


def load_all_trigger_po() -> (List[SceneTriggerPo], List[LUITriggerPo]):
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
        trigger_name=trigger['trigger_name'],
        event_name=trigger['event_name'],
        condition_script=trigger['condition_script'] if 'condition_script' in trigger else None
    )


def _build_lui_trigger_po(trigger: Dict) -> LUITriggerPo:
    return LUITriggerPo(
        trigger_id=trigger['trigger_id'],
        trigger_name=trigger['trigger_name'],
        trigger_corpus=trigger['trigger_corpus']
    )



# def create_new_lui_trigger_info(id, trigger_name, trigger_id, corpus_text: str) -> Optional[LUITriggerInfo]:
#     try:
#         embedding_client = OpenAIEmbedding()
#         embedding = embedding_client(input=corpus_text)
#         return LUITriggerInfo(id=id,
#                               trigger_name=trigger_name,
#                               trigger_id=trigger_id,
#                               corpus_text=corpus_text,
#                               embedding=embedding)
#     except Exception as e:
#         logger.exception(e)
#         return None
# def update_trigger_to_mongo(trigger_po: LUITriggerPo):
#     mongodb_client = MongoDBClient()
#     mongodb_client.update_many_document("AI_triggers", {"trigger_id": trigger_po.trigger_id}, {"$set": {"loaded_to_vector": "true"}})