from abc import ABC
from typing import ClassVar, List, Dict

from pydantic import BaseModel, Field


class Properties(BaseModel):
    type: str
    enum: List[str] = Field(default=None)
    description: str
    value = Field(default=None)


class Parameter(BaseModel):
    type: str
    properties: Dict[str, Properties] = Field(default={})
    required: List[str] = Field(default=None)


class FunctionDescribe(BaseModel):
    name: str
    description: str

    parameters: Parameter

    def gen_function_call_describe(self):
        data = self.dict(include={'parameters', 'name', 'description'}, exclude_none=True)
        return data

