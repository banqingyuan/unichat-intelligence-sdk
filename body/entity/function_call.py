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
    required: List[str] = Field(default=[])


def new_empty_parameter():
    return Parameter(
        type="object",
        properties={},
        required=[]
    )


class FunctionDescribe(BaseModel):
    name: str
    description: str

    parameters: Parameter = Field(default_factory=new_empty_parameter)
    output_params: Parameter = Field(default_factory=new_empty_parameter)

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

    def get_value(self, prop_name: str) -> Optional[str]:
        dance_name_prop = self.parameters.properties.get(prop_name, None)
        if not dance_name_prop or not dance_name_prop.value or dance_name_prop.value == '':
            return None
        return dance_name_prop.value

    def set_output_params(self, **kwargs):
        for name, prop in self.output_params.properties.items():
            if name in kwargs:
                prop.value = kwargs[name]

    def get_output_value(self, prop_name: str) -> Optional[str]:
        dance_name_prop = self.output_params.properties.get(prop_name, None)
        if not dance_name_prop or not dance_name_prop.value or dance_name_prop.value == '':
            return None
        return dance_name_prop.value