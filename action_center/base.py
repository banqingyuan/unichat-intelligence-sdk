import json
from abc import ABC, abstractmethod
from typing import List, Dict, ClassVar

from pydantic import BaseModel, Field


#   {
#         "name": "get_current_weather",
#         "description": "Get the current weather",
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "location": {
#                     "type": "string",
#                     "description": "The city and state, e.g. San Francisco, CA",
#                 },
#                 "format": {
#                     "type": "string",
#                     "enum": ["celsius", "fahrenheit"],
#                     "description": "The temperature unit to use. Infer this from the users location.",
#                 },
#             },
#             "required": ["location", "format"],
#         },
#     }

class Properties(BaseModel):
    type: str
    enum: List[str]
    description: str


class Parameter(BaseModel):
    type: str
    properties: Dict[str, Properties] = Field(default={})
    required: List[str] = Field(default=None)


class FunctionDescribe(BaseModel, ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    parameters: Parameter
    action_type: str = Field(default='chat')
    action_message: BaseModel

    def gen_function_call_describe(self):
        data = self.dict(include={'parameters'}, exclude_none=True)
        data['name'] = self.name
        data['description'] = self.description
        return json.dumps(data)

    @classmethod
    @abstractmethod
    def gen_func_instance(cls, **kwargs):
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not hasattr(self, 'name'):
            raise NotImplementedError('name is required')
        if not hasattr(self, 'description'):
            raise NotImplementedError('description is required')