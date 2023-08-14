from action_center.base import FunctionDescribe, Parameter


class WeatherForcast(FunctionDescribe):
    name = "weather_forcast"
    description = "Get the weather forcast of the city"

    @classmethod
    def gen_func_instance(cls, **kwargs) -> FunctionDescribe:
        return WeatherForcast(
            parameters=Parameter(
                type='object',
                properties={
                    "city": {
                        "type": "string",
                        "description": "The city name",
                        "default": "New York"
                    }
                }
            ),
            action_message=None,
        )