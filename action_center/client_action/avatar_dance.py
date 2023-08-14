from pydantic import BaseModel
from requests import Response

from action_center.action_model import Action_type_avatar_dance
from action_center.base import FunctionDescribe, Parameter


class AvatarDanceMessage(BaseModel):
    type: str = Action_type_avatar_dance
    dance_code: str = '1000'


class AvatarDance(FunctionDescribe):
    name = "make_avatar_dance"
    description = "Giving the command to start dancing"
    parameters = Parameter(
                type='object',
            )

    AID: str
    UID: str




if __name__ == '__main__':
    import requests

    url = "https://prod-181.westus.logic.azure.com/workflows/980d7dfa6959446dbb159d4a7ab0cd3c/triggers/manual/paths/invoke/weather/today?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=x6GTBvNAKXHgz_yRza1oKwZD3EZGNdK4hN9m34OGYYI"  # 注意：通常，POST请求不会发送到搜索引擎主页，这只是一个示例。

    headers = {
        "Content-Type": "application/json",  # 假设服务器期望的是JSON格式的数据
    }

    data = {
        "city": "New York"
    }

    response: Response = requests.post(url, headers=headers, json=data)

    print(response.status_code)
    print(response.text)
