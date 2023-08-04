import logging
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import md5

from common_py.client.azure_mongo import MongoDBClient
from common_py.client.embedding import OpenAIEmbedding
from common_py.client.pinecone_client import PineconeClientFactory
from common_py.utils.logger import wrapper_std_output

split_code = '*****'

logger = wrapper_std_output(logging.getLogger(__name__))


class KnowledgeLoader:

    def load_knowledge(self, knowledge_text: str):
        ids_res = self.mongo_client.find_from_collection("AI_tina_knowledge", projection=["_id"], filter={})
        ids = {}
        for id_item in ids_res:
            ids[str(id_item["_id"])] = True
        logger.debug(f"ids: {ids}")

        knowledge_block = knowledge_text.split(split_code)
        fresh_ids = []
        new_round_meta = md5(knowledge_text.encode()).hexdigest()
        with ThreadPoolExecutor(max_workers=10) as executor:
            for item in knowledge_block:
                if item == "":
                    continue
                md5_of_item = md5(item.encode()).hexdigest()
                fresh_ids.append(md5_of_item)
                if md5_of_item in ids:
                    ids.pop(md5_of_item)
                    logger.debug(f"knowledge item already exists: {md5_of_item}")
                    executor.submit(self._refresh_pinecone_metadata, md5_of_item, new_round_meta)
                    continue
                executor.submit(self._load_knowledge_item, item, md5_of_item, new_round_meta)
        if len(ids) > 0:
            self.mongo_client.delete_many_document("AI_tina_knowledge", {"_id": {"$nin": fresh_ids}})
            self.pinecone_client.delete_item(namespace="unichat_knowledge_database",
                                             filter={"valid_tag": {'$nin': [new_round_meta]}})

    def _refresh_pinecone_metadata(self, md5_of_item: str, new_round_meta: str):
        try:
            self.pinecone_client.set_metadata(id=md5_of_item,
                                              metadata={"text_key": md5_of_item,
                                                        "valid_tag": new_round_meta},
                                              namespace="unichat_knowledge_database")
        except Exception as e:
            logger.exception(f"refresh pinecone metadata failed: {e}")

    def _load_knowledge_item(self, item: str, md5_of_item: str, new_valid_tag: str):
        try:
            id = self.mongo_client.create_one_document("AI_tina_knowledge", {"_id": md5_of_item, "text": item})
            logger.debug(f"create knowledge item succeed: {id}")
            embedding = self.embedding_client(input=item)
            upsert_response = self.pinecone_client.upsert_index(id=md5(item.encode()).hexdigest(),
                                                                vector=embedding,
                                                                metadata={
                                                                    "text_key": md5_of_item,
                                                                    "valid_tag": new_valid_tag
                                                                },
                                                                namespace="unichat_knowledge_database")
            logger.debug(f"upsert knowledge item: {upsert_response}")
        except Exception as e:
            logger.exception(f"create knowledge item failed: {e}")

    def __init__(self):
        self.mongo_client: MongoDBClient = MongoDBClient()
        self.embedding_client: OpenAIEmbedding = OpenAIEmbedding()
        pinecone_factory = PineconeClientFactory()
        self.pinecone_client = pinecone_factory.get_client("knowledge-vdb", environment="us-west4-gcp-free")


if __name__ == "__main__":
    MongoDBClient(DB_NAME="unichat-backend")

    knowledge_text = """应用概述：这部分包含应用的基本信息
  1. 基本介绍：我们希望让朋友们能够随时随地跨越空间距离相聚，就像在现实中一样面对面交谈，观看视频，玩桌游。Unichat致力于打造一个无障碍、简洁直观的社交空间，让社交回归本质，回归人和人之间的直接交流。我们的愿景是将远程社交从二维升级为三维，通过XR技术，我们希望能还原甚至超越现实中的社交和聚会体验。
  2. 应用现在是1.0版本，我们会继续上线更多功能和桌游，敬请期待！
*****
Tina能力：详细介绍Tina的功能和能力。
  1. Tina可以回答各类问题
  2. 支持Language UI，可以直接对Tina说话，语音进行各种操作。
  3. 有反馈也可以和Tina说哦，会帮你转达
*****
应用交互：解释应用中各种交互的方式。
  1. 如何切换手势：将Quest 2手柄垂直放在桌面上，把手移到面前晃动，即可切换成手势操作。
  2. 呼出主菜单：左手张开手心朝向自己，捏合拇指和食指后松开
  3. 左手轮盘快速选择：左手张开手心朝向自己，捏合拇指和食指后向相应方向微微移动手后松开即可快捷操作。
  4. 调整高度：双手朝前，捏合双手拇指食指垂直向上或向下拖动，可以每次调整15cm高度。
  5. 调整角度或转向：
    1. 方案1：双手朝前，捏合双手拇指食指水平方向旋转；
    2. 方案二：右手微微抬起，手掌朝向左面，收紧中指无名指和小指，此时可以看到一个左右两边的箭头，微微调整手的位置然后捏合拇指食指即可实现转向
  6. 调整位置或瞬移：
    1. 方案1：双手朝前，捏合双手拇指食指水平方向同一方向拖拽，比如向后拖拽即可向前；
    2. 方案2：右手微微抬起，手掌朝向上方，收紧中指无名指和小指，此时可以看到一个弧线显示待传送的位置，微微调整手的位置然后捏合拇指食指即可实现瞬移。
*****
应用功能介绍：详细介绍每个功能，例如快速见面、桌游、浏览器、AI匹配、AI能量和会员相关。每个功能都应有详细的说明和操作步骤。
  1. 快速见面：
    1. 在主页点击在线好友头像进入详情页即可点击见面按钮
    2. 在主页点击好友房间即可快速加入
    3. 在发现页可以快速加入公开房间
*****
问：能更换Tina形象吗？
答：暂时不可以，后续会添加相应功能的！
*****
问：能给Tina换衣服吗？
答：暂时不可以，后续会添加相应功能的！
*****
问：如何提交反馈？
答： 如果想提交反馈，可以到这个页面，选择类别后直接说话即可。Unichat团队会做后续的跟进。
    也可以加入我们Discord群，群号为xxx，欢迎你！
*****
问：Unichat有哪些游戏？
答： 目前有五子棋和国际象棋，正在开发更多的桌游比如德州扑克和Uno，敬请期待！
*****
问：Unichat能做什么？
答： 可以随时随地和朋友一起浏览视频和听音乐，一起玩桌游，我们正在开发更多桌游，完全免费，敬请期待！
*****
问：开Unichat会员有什么用？
答： 可以有更长的AI和屏幕共享时长，详情可以去会员页查看
*****
问：为什么要限制AI聊天时长？
答： 因为AI所用的各种服务成本很高，成为会员可以覆盖您所使用的服务的一部分成本。
*****
问：为什么要限制共享浏览器时长？
答：因为共享浏览器的带宽费用很高，成为会员可以覆盖您所使用的服务的一部分成本。
*****
问: 如何添加好友？
答: 1. 可以在房间主页中查看对方资料后添加好友。
    2. 可以搜索朋友的Unichat ID来添加好友
*****
问：如何打开浏览器？
答：在App菜单点击浏览器打开
*****
问：如何共享浏览器？
答：点击浏览器下方共享按钮，即可共享
*****
LUI指示：说明如何使用语言用户界面，以及它可以完成的任务。
  1. 可以通过语音命令来直接进行操作，试试xxx
*****
隐私协议相关：详细介绍隐私协议，包括用户的数据将如何被收集和使用，以及用户如何能够控制自己的信息。
  1. 与AI的对话内容将可能被转成长期记忆储存起来，这个数据不会与任何第三方共享。
  2. 为了提升体验，我们只会处理匿名化的数据
  3. 如果您想清楚数据，可以删除该AI好友，30天后即自动清除。"""
    knowledge_loader = KnowledgeLoader()
    knowledge_loader.load_knowledge(knowledge_text)