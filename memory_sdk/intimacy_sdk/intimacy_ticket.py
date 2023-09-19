from pydantic import BaseModel


class IntimacyBase(BaseModel):
    """
    params:
    source_id: 亲密度归属
    target_id: 亲密度对象
    intimacy_from: 亲密度来源
    add_value: 亲密度增加值
    """
    source_id: str
    target_id: str
    intimacy_from: str
    add_value: int


class IntimacyTicketChatTime(IntimacyBase):
    intimacy_from = 'chat_time'  # 聊天时长对亲密度的贡献
    chat_time_length: float  # 具体聊天时长
    speaker: str  # 说话人 'AI' if AI, else speaker id
    UUID: str  # 对话事件一定存在UUID，可以根据UUID进行单据合并
    ts: int  # 时间戳表示事情发生的时刻

