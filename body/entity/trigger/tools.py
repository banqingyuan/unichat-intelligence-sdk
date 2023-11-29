from concurrent.futures import ThreadPoolExecutor

import uuid
from typing import Dict

from common_py.client.embedding import OpenAIEmbedding
from common_py.client.pg import delete_records_by_filter, batch_insert_vector, PgEngine
from common_py.dto.lui_trigger import LUITriggerInfo
from common_py.dto.lui_trigger import LUITrigger as LUITriggerDto

from body.entity.trigger.lui_trigger import LUITrigger


def load_LUI_trigger_to_vdb():
    trigger_lst: Dict[str, LUITrigger] = LUITriggerMgr().get_all_trigger()
    lui_lst = []
    tasks = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        for trigger in trigger_lst.values():
            for corpus_text in trigger.trigger_corpus:
                task = executor.submit(
                    create_new_lui_trigger_info,
                    **{
                        "id": str(uuid.uuid4()),
                        "trigger_name": trigger.trigger_name,
                        "trigger_id": trigger.trigger_id,
                        "corpus_text": corpus_text
                    }
                )
                tasks.append(task)
    for task in tasks:
        lui = task.result()
        lui_lst.append(lui)
    delete_records_by_filter(LUITriggerDto, {})
    batch_insert_vector(lui_lst, LUITriggerDto)


def create_new_lui_trigger_info(id, trigger_name, trigger_id, corpus_text: str) -> LUITriggerInfo:
    embedding_client = OpenAIEmbedding()
    embedding = embedding_client(input=corpus_text)
    return LUITriggerInfo(id=id,
                          trigger_name=trigger_name,
                          trigger_id=trigger_id,
                          corpus_text=corpus_text,
                          embedding=embedding)


if __name__ == '__main__':
    pg_config = {
        "host": "c.postgre-east.postgres.database.azure.com",
        # "host": "c-unichat-postgres-prod.q2t5np375m754a.postgres.cosmos.azure.com",
        "user": "citus",
        "db_name": "citus"
    }
    PgEngine(**pg_config)
    load_LUI_trigger_to_vdb()