from pydantic import BaseModel


Action_type_audio_message = "audio_message"
Action_type_audio_end_message = "audio_end_message"
Action_type_avatar_dance = "avatar_dance"


class AudioMessage(BaseModel):
    type: str = "audio_message"
    audio: str
    index: str
    uuid: str
    speaker_id: str


class AudioEndMessage(BaseModel):
    type: str = "audio_end_message"
    finish: bool = True
    index: str
    uuid: str
    speaker_id: str

