import json
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict

import uuid
from common_py.client.azure_mongo import MongoDBClient
from common_py.client.embedding import OpenAIEmbedding
from common_py.client.pg import batch_insert_vector, PgEngine, query_vector_info
from common_py.dto.ai_action_vector import ActionVectorInfo, ActionVector, create_new_action_vector_info

all_action_json_str = """
[
    {"id": 9100, "description": "Leaning forward with hands on waist in an angry or confrontational manner. A static pose.", "gender": "Female"},
    {"id": 9101, "description": "Standing with fists clenched in front, signaling aggression or anger. A static pose.", "gender": "Female"},
    {"id": 9102, "description": "An action of being very angry and impatiently complaining.", "gender": "All"},
    {"id": 9103, "description": "An action of using two fingers to point at the head and spin around, indicating anger and the need to think.", "gender": "All"},
    {"id": 9104, "description": "A cute action of saying goodbye with a large arm swing.", "gender": "Female"},
    {"id": 9105, "description": "An action of waving goodbye with a large arm swing.", "gender": "Male"},
    {"id": 9106, "description": "A cute action of waving goodbye with both hands.", "gender": "Female"},
    {"id": 9107, "description": "An action of waving goodbye.", "gender": "All"},
    {"id": 9108, "description": "An action of waving goodbye.", "gender": "All"},
    {"id": 9109, "description": "An action of clapping hands enthusiastically, indicating excitement", "gender": "Female"},
    {"id": 9110, "description": "An action of looking down and counting on fingers.", "gender": "All"},
    {"id": 9111, "description": "A sad emotional action of sitting down, covering the face and crying.", "gender": "All"},
    {"id": 9112, "description": "A sad emotional action of sitting down, covering the face and crying.", "gender": "All"},
    {"id": 9113, "description": "A sad emotional action of sitting down, covering the face and crying.", "gender": "All"},
    {"id": 9114, "description": "An action of standing, crying and wiping tears.", "gender": "All"},
    {"id": 9115, "description": "Hands placed in front of chest and oriented forward, mimicking a cat, acting cute or endearing.", "gender": "Female"},
    {"id": 9116, "description": "A quick action of stretching out both hands to make a scissors sign, acting cute.", "gender": "Female"},
    {"id": 9117, "description": "A cute action of placing both hands on top of the head to imitate a rabbit.", "gender": "Female"},
    {"id": 9118, "description": "An action of making a hook with the hand and placing it beside the head, mimicking a small animal.", "gender": "Female"},
    {"id": 9119, "description": "An action of placing both hands on the sides of the face, acting cute.", "gender": "Female"},
    {"id": 9120, "description": "A cute action of covering the face with both hands and shaking the head left and right.", "gender": "Female"},
    {"id": 9121, "description": "A shy action of covering the face and sneaking a peek to the side.", "gender": "Female"},
    {"id": 9122, "description": "A cute gesture showing approval or appreciation.", "gender": "Female"},
    {"id": 9123, "description": "A cute action of putting both hands together to make a heart shape.", "gender": "Female"},
    {"id": 9124, "description": "An action of quickly making several heart symbols with both hands by crossing the thumb and index finger, showing love", "gender": "All"},
    {"id": 9125, "description": "An action of making a heart symbol with one hand. Showing love", "gender": "All"},
    {"id": 9126, "description": "A cute action of bending over, making a 'shush' sign and striking a pose.", "gender": "Female"},
    {"id": 9127, "description": "An action of dancing to the rhythm.", "gender": "Female"},
    {"id": 9128, "description": "An action of performing a series of aerobics stretches and poses.", "gender": "Female"},
    {"id": 9129, "description": "An action of dancing crazy steps, a bit manic.", "gender": "Female"},
    {"id": 9130, "description": "An energetic action of dancing, spinning, and raising hands in excitement.", "gender": "All"},
    {"id": 9131, "description": "An action of jumping up in extreme excitement.", "gender": "All"},
    {"id": 9132, "description": "An action of excitedly waving arms up and down.", "gender": "Female"},
    {"id": 9133, "description": "An action of spinning around excitedly.", "gender": "Female"},
    {"id": 9134, "description": "An action of excitedly putting hands on hips and twisting left and right.", "gender": "Female"},
    {"id": 9135, "description": "An action of excitedly moving left and right, spreading arms to show off.", "gender": "Female"},
    {"id": 9136, "description": "Open arms waiting for a hug", "gender": "Female"},
    {"id": 9137, "description": "A cheerful action of tilting the head and waving.", "gender": "Female"},
    {"id": 9138, "description": "An action of waving to greet someone while standing.", "gender": "All"},
    {"id": 9139, "description": "An action of quickly waving to greet someone while standing.", "gender": "All"},
    {"id": 9140, "description": "An action of bending over to bow and greet.", "gender": "All"},
    {"id": 9141, "description": "An action indicating a victory-like joy (male).", "gender": "Male"},
    {"id": 9142, "description": "An action of excitedly dancing (female).", "gender": "Female"},
    {"id": 9143, "description": "An action of excitedly dancing (male).", "gender": "Male"},
    {"id": 9144, "description": "An action of excitedly dancing (female).", "gender": "Female"},
    {"id": 9145, "description": "An action of joyfully twisting left and right (male).", "gender": "Male"},
    {"id": 9146, "description": "An action of joyfully twisting left and right (female).", "gender": "Female"},
    {"id": 9147, "description": "A hesitant or reluctant body swing or sway, indicating unwillingness or hesitation.", "gender": "Female"},
    {"id": 9148, "description": "A cute action of blowing a kiss after kissing the hand.", "gender": "Female"},
    {"id": 9149, "description": "A romantic action of leaning forward to kiss, with both arms supporting the other person's shoulders.", "gender": "Female"},
    {"id": 9150, "description": "An action of sending a flying kiss with both hands. Showing love.", "gender": "All"},
    {"id": 9151, "description": "An action of sending a flying kiss with one hand. Showing love.", "gender": "All"},
    {"id": 9152, "description": "Stands in place, laughing and looking downwards. Signaling joy and amusement.", "gender": "All"},
    {"id": 9153, "description": "Stands in place, laughing and looking upwards. Signaling happiness and lightheartedness.", "gender": "All"},
    {"id": 9154, "description": "An action of looking around.", "gender": "Female"},
    {"id": 9155, "description": "An action of looking around.", "gender": "Male"},
    {"id": 9156, "description": "A slow and thoughtful looks towards the lower left corner. A sign of contemplation or introspection.", "gender": "All"},
    {"id": 9157, "description": "Looks angrily towards the upper left corner. A sign of frustration or disagreement.", "gender": "All"},
    {"id": 9158, "description": "An action of looking back from the right side.", "gender": "All"},
    {"id": 9159, "description": "An action of looking back from the right side.", "gender": "All"},
    {"id": 9160, "description": "An action of nervously praying with clasped hands.", "gender": "All"},
    {"id": 9161, "description": "Nods once. Affirmation or agreement with what is being discussed or presented.", "gender": "All"},
    {"id": 9162, "description": "Nods twice. Strong affirmation or agreement, emphasize a point or statement.", "gender": "All"},
    {"id": 9163, "description": "An action of nodding in agreement with a large wave of the hand.", "gender": "Male"},
    {"id": 9164, "description": "An action of spreading both hands wide to indicate indifference.", "gender": "Male"},
    {"id": 9165, "description": "Right hand touching the back of the neck, a pose signaling slight embarrassment or admitting a mistake. This can be used as a photo pose.", "gender": "All"},
    {"id": 9166, "description": "Right hand on chest, signaling bravery. This can be used as a photo pose.", "gender": "All"},
    {"id": 9167, "description": "Hands resting on the back. This can be used as a photo pose.", "gender": "All"},
    {"id": 9168, "description": "Hands resting on the front. This can be used as a photo pose.", "gender": "All"},
    {"id": 9169, "description": "A cute and playful posture that's ideal for a photo shoot.", "gender": "All"},
    {"id": 9170, "description": "A confident stance with the left hand on the waist, suitable for a stylish photo shoot.", "gender": "All"},
    {"id": 9171, "description": "A stance with hands open in front, good for a straightforward photo shoot.", "gender": "All"},
    {"id": 9172, "description": "A lively stance with the right fist raised, perfect for an energetic photo session.", "gender": "All"},
    {"id": 9173, "description": "A lively and playful pose with the right hand making a scissors sign, perfect for a fun and energetic photo shoot.", "gender": "All"},
    {"id": 9174, "description": "A joyful stance that captures a moment of laughter, great for a cheerful photo shoot.", "gender": "All"},
    {"id": 9175, "description": "A humble or remorseful stance, like after making a mistake, suitable for an expressive photo session.", "gender": "All"},
    {"id": 9176, "description": "A flirtatious stance with the right hand pointing, perfect for a provocative photo shoot.", "gender": "All"},
    {"id": 9177, "description": "A seductive stance with the right hand resting behind the body, suitable for a sultry photo shoot.", "gender": "All"},
    {"id": 9178, "description": "An enticing stance with a forward lean, perfect for a seductive photo shoot.", "gender": "All"},
    {"id": 9179, "description": "A stance that captures an expression of surprise with hands open in front, great for a dynamic photo shoot.", "gender": "All"},
    {"id": 9180, "description": "A contemplative stance that conveys deep thought, suitable for a thoughtful or intellectual photo shoot.", "gender": "All"},
    {"id": 9181, "description": "An action displaying frustration by pointing a finger.", "gender": "Female"},
    {"id": 9182, "description": "A slow, cute action of pointing at someone with a finger.", "gender": "Female"},
    {"id": 9183, "description": "An action of praying with hands together.", "gender": "All"},
    {"id": 9184, "description": "An action of placing both hands in front of the face to express expectation.", "gender": "All"},
    {"id": 9185, "description": "An action of making a praying or wishing gesture by quickly shaking hands held together.", "gender": "All"},
    {"id": 9186, "description": "A cute action of tilting the body and placing both hands at the mouth to request.", "gender": "All"},
    {"id": 9187, "description": "An action of shaking the head, indicating disagreement.", "gender": "All"},
    {"id": 9188, "description": "An action of semi-squatting and joining hands to make a gesture of shooting a ki blast.", "gender": "All"},
    {"id": 9189, "description": "An action of semi-squatting and joining hands to make a gesture of shooting a ki blast.", "gender": "All"},
    {"id": 9190, "description": "An action of semi-squatting and joining hands to make a gesture of shooting a ki blast.", "gender": "All"},
    {"id": 9191, "description": "An action of shaking the head and waving hands to refuse.", "gender": "All"},
    {"id": 9192, "description": "An action of pushing forward with both hands to indicate refusal.", "gender": "All"},
    {"id": 9193, "description": "A gesture of swinging one hand forward, similar to saying 'don't mention it'.", "gender": "All"},
    {"id": 9194, "description": "An action of covering the face in regret.", "gender": "All"},
    {"id": 9195, "description": "An action of covering the face in despair.", "gender": "All"},
    {"id": 9196, "description": "An action of first covering the mouth, then the face in despair, a long action.", "gender": "All"},
    {"id": 9197, "description": "An action of bending over and lowering the head to express sadness.", "gender": "All"},
    {"id": 9198, "description": "An action of hanging one's head in dismay, rubbing feet on the ground.", "gender": "All"},
    {"id": 9199, "description": "A gesture suggesting indifference or confusion.", "gender": "All"},
    {"id": 9200, "description": "A self-mocking action of first holding the head, then spreading arms to indicate self-mockery like I suck.", "gender": "All"},
    {"id": 9201, "description": "An action of holding the head with both hands in surprise.", "gender": "All"},
    {"id": 9202, "description": "An action of covering the mouth with the left hand in surprise.", "gender": "All"},
    {"id": 9203, "description": "An action of spreading both hands to express surprise.", "gender": "All"},
    {"id": 9204, "description": "An action of placing the right hand over the heart and nodding in thanks.", "gender": "All"},
    {"id": 9205, "description": "An action of pointing the thumb down to indicate a negative response.", "gender": "All"},
    {"id": 9206, "description": "An action of pointing both thumbs up in praise.", "gender": "All"},
    {"id": 9207, "description": "An action of extending one hand and giving a thumbs up to express praise.", "gender": "All"},
    {"id": 9208, "description": "A curious or doubtful action of tilting the head to the right.", "gender": "All"},
    {"id": 9209, "description": "An action of covering the mouth with a hand while yawning.", "gender": "All"},
    {"id": 9210, "description": "An action of covering the mouth with a hand while yawning.", "gender": "All"},
    {"id": 9211, "description": "An action of turning the head to the left, indicating anger or avoidance.", "gender": "All"},
    {"id": 9212, "description": "An action of turning the head to the right, indicating anger or avoidance.", "gender": "All"},
    {"id": 9213, "description": "An action of first covering the face and then spreading hands to indicate disbelief.", "gender": "Female"},
    {"id": 9214, "description": "A swift hand wave, signaling goodbye.", "gender": "All"},
    {"id": 9215, "description": "An action of looking in a small mirror to touch up the foundation.", "gender": "Female"},
    {"id": 9216, "description": "An action of raising the right hand energetically, symbolizing victory.", "gender": "Female"}
]
"""


def load_animation_to_mongo():
    all_action_json_lst: List = json.loads(all_action_json_str)
    mongoClient = MongoDBClient(DB_NAME="unichat-backend")
    mongoClient.create_document("AI_animation_storage", all_action_json_lst)


def load_animation_from_mongo_to_vdb():
    mongoClient = MongoDBClient(DB_NAME="unichat-backend")
    res_lst = mongoClient.find_from_collection(collection_name="AI_animation_storage", filter={})
    tasks = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        for res in res_lst:
            task = executor.submit(
                create_new_action_vector_info,
                **{
                    "client_id": res['id'],
                    "description": res['description'],
                    "gender": res['gender']
                }
            )
            tasks.append(task)
    animation_lst = []
    for task in tasks:
        animation = task.result()
        animation_lst.append(animation)
    batch_insert_vector(animation_lst, ActionVector)

    return res


class AnimationMgr():
    _instance_lock = threading.Lock()

    gender_map = {
        'male': 1,
        'female': 2,
    }

    def __init__(self):
        if not hasattr(self, "_ready"):
            AnimationMgr._ready = True

    def load_animation_from_vdb(self, input_data: str, gender: str) -> List[ActionVectorInfo]:
        gender_lst = [0]
        if gender != '':
            gender_lst.append(self.gender_map[gender.lower()])
        res_lst = query_vector_info(model=ActionVector,
                          input_data=input_data,
                          meta_filter={
                              'gender': {'$in': gender_lst}
                          },
                          top_k=10,
                          threshold=0.6,
                          )
        info_lst = []
        for res in res_lst:
            info = ActionVectorInfo(**res)
            info_lst.append(info)
        return info_lst



    def __new__(cls, *args, **kwargs):
        if not hasattr(AnimationMgr, "_instance"):
            with AnimationMgr._instance_lock:
                if not hasattr(AnimationMgr, "_instance"):
                    AnimationMgr._instance = object.__new__(cls)
        return AnimationMgr._instance


if __name__ == '__main__':
    pg_config = {
        "host": "c.postgre-east.postgres.database.azure.com",
        # "host": "c-unichat-postgres-prod.q2t5np375m754a.postgres.cosmos.azure.com",
        "user": "citus",
        "db_name": "citus"
    }
    PgEngine(**pg_config)
    # mongoClient = MongoDBClient(DB_NAME="unichat-backend")
    # load_animation_from_mongo_to_vdb()
    AnimationMgr().load_animation_from_vdb("hello", 'female')
