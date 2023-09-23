import logging
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import md5
from typing import List

from common_py.client.embedding import OpenAIEmbedding
from common_py.client.pg import update_by_id, query_vector_info, PgEngine, batch_insert_vector, delete_records_by_filter
from common_py.dto.unicaht_knowledge import UnichatKnowledge, UnichatKnowledgeInfo, load_all_knowledge
from common_py.utils.logger import wrapper_std_output, wrapper_azure_log_handler

split_code = '*****'

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

class KnowledgeLoader:

    def load_knowledge(self, knowledge_text: str):

        res = load_all_knowledge()
        ids = {}
        for item in res:
            ids[item.id] = True
        logger.debug(f"ids: {ids}")

        knowledge_block = knowledge_text.split(split_code)
        fresh_ids = []
        new_round_meta = md5(knowledge_text.encode()).hexdigest()
        tasks = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            for item in knowledge_block:
                if item == "":
                    continue
                md5_of_item = md5(item.encode()).hexdigest()
                fresh_ids.append(md5_of_item)
                if md5_of_item in ids:
                    ids.pop(md5_of_item)
                    logger.debug(f"knowledge item already exists: {md5_of_item}")
                    executor.submit(self._refresh_pgvector_metadata, md5_of_item, new_round_meta)
                    continue
                task = executor.submit(self._load_knowledge_item, item, md5_of_item, new_round_meta)
                tasks.append(task)
        items: List[UnichatKnowledgeInfo] = []
        for task in tasks:
            item = task.result()
            if isinstance(item, UnichatKnowledgeInfo):
                items.append(item)
        batch_insert_vector(
            model_cls=UnichatKnowledge,
            data_list=items,
        )
        # if len(ids) > 0:
        #     # self.mongo_client.delete_many_document("AI_tina_knowledge", {"_id": {"$nin": fresh_ids}})
        delete_records_by_filter(UnichatKnowledge,
                                         {"valid_tag": {'$nin': [new_round_meta]}})

    def _refresh_pgvector_metadata(self, md5_of_item: str, new_round_meta: str):
        try:
            update_by_id(
                model_cls=UnichatKnowledge,
                record_id=md5_of_item,
                update_fields={'valid_tag': new_round_meta}
            )
        except Exception as e:
            logger.exception(f"refresh pgvector AI knowledge metadata failed: {e}")

    def _load_knowledge_item(self, item: str, md5_of_item: str, new_valid_tag: str):
        try:
            knowledge_info = UnichatKnowledgeInfo(
                id=md5_of_item,
                text=item,
                embedding=self.embedding_client(input=item),
                valid_tag=new_valid_tag
            )
            return knowledge_info
        except Exception as e:
            logger.exception(f"create knowledge item failed: {e}")

    def __init__(self):
        self.embedding_client: OpenAIEmbedding = OpenAIEmbedding()


if __name__ == "__main__":
    pg_config = {
        "host": "c-unichat-postgres-prod.q2t5np375m754a.postgres.cosmos.azure.com",
        "user": "citus",
        "db_name": "citus"
    }
    PgEngine(**pg_config)

    knowledge_text = """Application Overview (Basic introduction to the app; its purpose; what it does)
    1. Basic Introduction: We aspire to let friends gather quickly across spatial distances anytime and anywhere, chatting face-to-face, watching videos, and playing board games together, just like in real life. We aim to bring socializing back to its essence, emphasizing direct communication between individuals.
    2. The app is currently at version 1.0. Stay tuned as we will be releasing more features and board games!
*****
Tina's Abilities (Features and capabilities of Tina; how to use Tina; its utilities)
    1. Tina can answer various questions about the app.
    2. Sonn will supports Language UI, allowing users to talk directly to Tina and perform various operations via voice commands.
    3. If you have feedback, you can tell Tina, and she will relay the message.
*****
Interaction: Switching to hand gestures: Place the Quest 2 controller vertically on the desk, wave your hand in front, and the mode will switch to hand gestures.
*****
Interaction: Accessing main menu: Open your left hand with the palm facing you, pinch the thumb and index finger together, then release.
*****
Interaction: Left-hand quick select: Open your left hand with the palm facing you, pinch the thumb and index finger, then slightly move your hand in the desired direction for quick access.
*****
Interaction: Adjusting height: Extend both hands forward, pinch both thumbs and index fingers, then drag vertically to adjust by 15cm increments.
*****
Interaction: Adjusting angle or direction or turn:
        a. Option 1: Extend both hands forward, pinch and rotate the thumbs and index fingers horizontally.
        b. Option 2: Slightly raise the right hand with the palm facing left, curl the middle, ring, and pinky fingers. Arrows will appear on both sides; adjust hand position slightly, pinch thumb and index finger to turn.
*****
Interaction: Moving, positioning, or teleporting:
        a. Option 1: Extend both hands forward, pinch and drag thumbs and index fingers horizontally in the same direction. Dragging backward will move you forward.
        b. Option 2: Slightly raise your right hand with the palm facing upwards, curl the middle, ring, and pinky fingers. A trajectory line will show the teleporting position; adjust hand position slightly, then pinch thumb and index finger to teleport.
*****
Application Features (Detailed introduction of each feature, such as quick meet-up, board games, browser, AI matching, AI energy, and membership-related)
    1. Quick Meet-Up (How to meet friends)
        a. Click on online friends' name on the main menu, then click the join button in the details page.
        b. Join friends' rooms directly from the main menu.
        c. Join public rooms quickly from the explore page.
    2. Games (What board games and games are included in Unichat)
        a. Currently, we have Chat Card game and Gomoku. More games will be added soon!
    3. Browser (How to use the browser, is sharing possible?)
        a. We will soon support shared browser so you can watch videos with friends.
*****
FAQs:
Q: Can Tina's avatar be changed?
A: Not currently, but we'll be adding this feature soon!
*****
Q: Can we change Tina's clothing?
A: Not at the moment, but we plan to introduce this feature in the future!
*****
Q: How to submit feedback?
A: If you wish to provide feedback, go to setting and send email. The Unichat team will follow up. You can also join our Discord group, the group ID is in the setting page.
*****
Q: Which games are available in Unichat?
A: Currently, we offer Gomoku and Chat Cards, and we're in the process of developing more board games like Texas Hold'em and Uno. Stay tuned!
*****
Q: What can Unichat do?
A: You can watch videos and listen to music with friends anytime, anywhere, and play board games together. We are developing more board games, all for free, so stay tuned!
*****
Q: What are the benefits of becoming a Unichat member?
A: Members get more chat energy and extended screen-sharing time. Details can be found on the membership page.
*****
Q: Why is AI chat time limited? Why does chatting with you (AI) consume energy? Why energy is so expensive? Why energy consumes so fast? 
A: The services used for chatting with AI, including me, are quite costly. Including LLM and TTS costs. We may lower the price when cost can be lower.
*****
Q: How to calculate energy consumption? How does energy convert to AI
A: Energy use is based on voice message length, with 100 points equalling 300 seconds. Actual conversation length might be 1.5 to 2 times the calculated length, depending on the content and speed of the conversation.
*****
Q: Why is the browser sharing time restricted?
A: The bandwidth cost for shared browsing is high. Becoming a member helps cover a portion of the service costs.
*****
Q: How do I add friends?
A: 1. You can view profiles in room homepage and add friends from there.
2. Search for your friend's Unichat ID to add them.
*****
Q: How can I modify my user ID?
A: Go to the settings page and click on the personal homepage to modify.
*****
Q: How to open the browser?
A: Click on the browser in the App menu.
*****
Q: How to share the browser?
A: Click the share button below the browser to share.
*****
Q: How to use Language User Interface? What is LUI?
A: You can operate directly through voice commands, e.g., open browser.
*****
Privacy Policy Related (how data will be used; person infomation-related):
    1. Conversations with the AI might be stored as long-term memory but won't be shared with any third parties.
    2. To enhance the user experience, we may process anonymized data.
    3. If you wish to erase the data, delete the AI or close your account, and data will automatically be cleared after 30 days."""
    knowledge_loader = KnowledgeLoader()
    knowledge_loader.load_knowledge(knowledge_text)
