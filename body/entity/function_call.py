from abc import ABC
from typing import ClassVar, List, Dict, Optional

from pydantic import BaseModel, Field


class Properties(BaseModel):
    type: str
    enum: List[str] = Field(default=None)
    description: str
    value: str = Field(default=None)


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

    def if_props_ready(self) -> bool:
        # check if all required props are ready
        for name, prop in self.parameters.properties.items():
            if name in self.parameters.required and prop.value is None:
                return False
        return True

    def set_params(self, **kwargs):
        for name, prop in self.parameters.properties.items():
            if name in kwargs:
                prop.value = kwargs[name]
