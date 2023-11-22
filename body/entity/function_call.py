import logging
from typing import List, Dict, Optional

from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from pydantic import BaseModel, Field

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)

class Properties(BaseModel):
    type: str
    enum: List[str] = Field(default=None)
    description: str
    value: str = Field(default=None)


class Parameter(BaseModel):
    type: str
    properties: Dict[str, Properties] = Field(default={})
    required: List[str] = Field(default=[])

    def get_prop_value(self, prop_name: str):
        prop = self.properties.get(prop_name, None)
        if prop:
            return prop.value
        return None


def combine_parameters(params: List[Parameter]) -> Parameter:
    """
    合并多个参数，如果有重复的，以后面的为准
    :param params:
    :return:
    """
    if not params:
        return new_empty_parameter()
    if len(params) == 1:
        return params[0]
    new_params = Parameter(
        type="object",
        properties={},
        required=[]
    )
    for param in params:
        for name, prop in param.properties.items():
            if name in new_params.properties:
                logger.warning(f"param {name} already exists, will be overwritten")
            new_params.properties[name] = prop
        for name in param.required:
            if name not in new_params.required:
                new_params.required.append(name)
    return new_params


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
        # 所有value设置过的都是预置参数，不需要填充
        params = self.parameters.dict(exclude_none=True)
        for name, prop in self.parameters.properties.items():
            if prop.value is not None:
                del params['properties'][name]
        describe = {
            "name": self.name,
            "description": self.description,
            "parameters": params
        }
        return describe

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


if __name__ == '__main__':
    fd = FunctionDescribe(name="test", description="test", parameters=Parameter(type="object", properties={
        "test": Properties(type="string", description="test", value="test"),
        "testB": Properties(type="string", description="test"),
    }))
    print(fd.gen_function_call_describe())