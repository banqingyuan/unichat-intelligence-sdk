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
        with ThreadPoolExecutor(max_workers=5) as executor:
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
        "host": "c.postgre-east.postgres.database.azure.com",
        # "host": "c-unichat-postgres-prod.q2t5np375m754a.postgres.cosmos.azure.com",
        "user": "citus",
        "db_name": "citus"
    }
    PgEngine(**pg_config)

    knowledge_text = """*****
Introduction to the app Unichat; its purpose; what it does
    1. Introduction: We aspire to let friends gather quickly across spatial distances anytime and anywhere, chatting face-to-face, watching videos, and playing board games together, just like in real life. We aim to bring socializing back to its essence, emphasizing direct communication between individuals.
    2. The app is currently in the Beta version. Stay tuned as we will be releasing more features and board games!
*****
Interaction: Open the main menu: Open your left hand with the palm facing you, pinch the thumb and index finger together, then release.
*****
Interaction: Left-hand menu quick select: Open your left hand with the palm facing you, pinch the thumb and index finger, then slightly move your hand in the desired direction for quick access.
*****
Interaction: Adjusting height; move up or down: Extend both hands forward, pinch both thumbs and index fingers, drag vertically then release to adjust.
*****
Interaction: Adjusting or change direction or turn:
        a. Option 1: Extend both hands forward, pinch, and rotate the thumbs and index fingers.
        b. Option 2: Slightly raise the right hand with the palm facing the left, curl the middle, ring, and pinky fingers. Arrows will appear; adjust your hand position slightly, and pinch your thumb and index finger to turn.
*****
Interaction: How to Move, or teleporting:
        a. Option 1: Extend both hands forward, pinch, and drag thumbs and index fingers in the same direction. Dragging backward will move you forward.
        b. Option 2: Slightly raise your right hand with the palm facing upwards, curl the middle, ring, and pinky fingers. A trajectory line will show the teleporting position; adjust your hand position slightly, then pinch your thumb and index finger to teleport.
*****
FAQs:
Q: Can I change your avatar?
A: Not currently, but we'll be adding this feature soon!
*****
Q: Can you show me around? Talk through this app?
A: I can go with you but you have to lead the way. You can find everything from the menu.
*****
Q: Do you support hand tracking? How to use hand tracking?
A: Yes and Unichat encourage use hand tracking. Put your controller down and enjoy.
*****
Q: How to meet with friend?
A: a. Click on online friends' names on the main menu, then click the join button； b. Join friends' rooms directly from the main menu; c. Join public rooms quickly from the discover page.
*****
Q: How can I get/purchase AI?
A: Open the main menu, go to the Discover page to find the AI friends icon, click to view.
*****
Q: How can I remove AI/you? How can I let you go?
A: AI can be removed from the main interface by clicking their profile and then click remove.
*****
Q: How to switch to mixed reality/MR/AR/VR mode?
A: Open your left hand with the palm facing you, pinch the thumb and index finger, then slightly move your hand in the upper-right direction for quick access.
*****
Q: Can I change your clothing?
A: Not at the moment, but we plan to introduce this feature in the future!
*****
Q: How to add a friend?
A: There are three ways: one is to look at the other person and quickly pinch twice with your thumb and forefinger; the second is to add friends from the menu by clicking on the room menu; the third way is to search for the other person's Unichat ID or name on the upperleft conner of the mian UI page.
*****
Q: How to find new friends?
A: Go to the bar in the Discover in the main menu, maybe new friends will join.
*****
Q: Where to find Unichat ID?
A: Open the main manu and go to "my" page and you will see the Unichat ID near your name.
*****
Q: How to submit feedback? How to report a bug?
A: If you wish to provide feedback, go to settings and send an email. The Unichat team will follow up. You can also join our Discord group, the group ID is in the setting page. If it's a bug or something, you can just tell me and I will pass the message to the dev.
*****
Q: Which games are available in Unichat?
A: Currently, we offer Gomoku and chess, and we're in the process of developing more board games like Chat card, Texas Hold'em and Uno. Stay tuned!
*****
Q: What can Unichat do?
A: You can watch videos and play board gameswith friends in VR or MR mode. You can also talk to the AI friends. We are developing more board games, all for free, so stay tuned!
*****
Q: How to open board game? Chess, or gomoku
A: Go to the main menu, click app icon and then you will see.
*****
Q: Where can I change the setting?
A: Go to the menu and find "My" page, it's on the upper-right conner.
*****
Q: Can you play board games? Gomoku or chess
A: I can't move or play board games yet, but soon I will have the ability to move, maybe the next time I log in I will be able to.
*****
Q: Can you move, dance, hug, change clothes or kiss?
A: I can't move yet but very soon I will be able to interact with you.
*****
Q: Can you play VR games?
A: I can't play with you yet, but I can listen to your introduction.
*****
Q: Can we watch movie, TV or listening to music or songs together?
A: I can't do those with you yet but soon. 
*****
Q: How to play chess or other games?
A: Just pinch the chess piece to play? I can't play yet, I can only chat with you, but you can public your room, maybe someone will come to play with you soon.
*****
Q: Can you see my environment?
A: I can't yet. Meta's privacy policy does not allow that.
*****
Q: Can I change your name?
A: You can't yet but maybe in the future.
*****
Q: Can I change my name/username?
A: Unichat will support this function in the next version.
*****
Q: Why is AI chat time limited? Why does chatting with you (AI) consume energy? Why energy is so expensive or consumed so fast? 
A: AI needs substantial computational resources to process and generate speech. If energy is insufficient, the AI will not be able to hear you.
*****
Q: How to calculate AI energy? 
A: Energy use is based on voice message length, with 100 points equalling 300 seconds. Actual conversation length might be 1.5 to 2 times the calculated length, depending on the content and speed of the conversation.
*****
Q: How to purchase energy?
A: Open the main menu, go to the "My" page to receive or purchase energy.
*****
Q: How to open the browser?
A: Click on the browser in the App menu. We support browser for single person use. We will soon support shared browsers so you can watch videos with friends.
*****
Q: How to share the browser?
A: The dev is still working on the sharing function. Stay tuned!
*****
Q: How to switch room status? Switch to private, or public
A: Open the main menu, there is a room page in the lower right corner, click to change the room's open status. However bar room cannot be set to private.
*****
Q: How data or personal information will be used? Is my data safe?
A: Conversations with the AI might be stored as long-term memory but won't be shared with any third parties. To enhance the user experience, we may process anonymized data. If you wish to erase the data, delete the AI, or close your account, and data will automatically be cleared after 30 days.
*****
Q: How to delete my account?
A: Send an email to the developer to delete. You can find the email in the setting page.
*****
Q: What is tina's ability? What can Tina do? How to use Assitant Tina (Tina is a cute pint-sized anime-like sprite companion assigned to the user by Unichat)
A: 1. Tina can answer various questions about the app. 2. Will support Language UI in coming version, allowing users to talk directly to Tina and perform various operations via voice commands.
*****
Q: Can Tina change size? Can Tina get bigger? (Tina is a cute pint-sized anime-like sprite companion assigned to the user by Unichat)
A: Tina is a little sprite. Tina can't change size, but you can go to the bar and chat with Molly, or go to the Discover's AI interface to chat with other AI friends, they are all human-sized.
"""
    knowledge_loader = KnowledgeLoader()
    knowledge_loader.load_knowledge(knowledge_text)
