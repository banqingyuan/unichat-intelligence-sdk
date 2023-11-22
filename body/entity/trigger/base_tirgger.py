from pydantic import BaseModel


class BaseTrigger(BaseModel):
    typ: str