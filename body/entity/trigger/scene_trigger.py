import logging

from common_py.dto.ai_instance import InstanceMgr, AIBasicInformation
from common_py.dto.user import UserInfoMgr, UserBasicInformation
from common_py.model.scene.scene import SceneEvent
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

from body.entity.trigger.base_tirgger import BaseTrigger
from memory_sdk.hippocampus import HippocampusMgr, Hippocampus
from memory_sdk.memory_entity import UserMemoryEntity

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class SceneTrigger(BaseTrigger):
    typ = 'scene_trigger'
    trigger_name: str
    trigger_id: str
    condition_script: str

    def eval_trigger(self, trigger_event: SceneEvent) -> bool:
        if trigger_event.event_name != self.trigger_name:
            return False
        if not self.condition_script or self.condition_script.strip() == "":
            return True
        input_params = {
            'trigger_event': trigger_event,
            'hit': False,
            'user_info': None,
            'AI_info': None,
            'hippocampus': None,
            'AI_memory_of_user': None,
        }
        UID = trigger_event.get_UID()
        if UID:
            user_info: UserBasicInformation = UserInfoMgr().get_instance_info(UID)
            input_params['user_info'] = user_info
        AID = trigger_event.AID
        if AID:
            AI_info: AIBasicInformation = InstanceMgr().get_instance_info(AID)
            input_params['AI_info'] = AI_info
        if UID and AID:
            hippocampus: Hippocampus = HippocampusMgr().get_hippocampus(AID)
            if hippocampus:
                input_params['hippocampus'] = hippocampus
                AI_memory_of_user: UserMemoryEntity = hippocampus.load_memory_of_user(UID)
                input_params['AI_memory_of_user'] = AI_memory_of_user

        try:
            exec(self.condition_script, input_params)
        except Exception as e:
            logger.exception(e)
            return False
        return input_params['hit']


def ScriptPlayground(
        trigger_event: SceneEvent,
        hit: bool,
        user_info: UserBasicInformation,
        AI_info: AIBasicInformation,
        hippocampus: Hippocampus,
        AI_memory_of_user: UserMemoryEntity):

    pass
