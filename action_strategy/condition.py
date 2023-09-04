from pydantic import BaseModel


# type Condition struct {
# 	// 条件ID
# 	ConditionId int64 `json:"condition_id"`
# 	// 条件生效时间，继承策略的生效时间
# 	StartEffect int64 `json:"start_effect"`
# 	// 条件失效时间，继承策略的失效时间
# 	EndEffect int64 `json:"end_effect"`
# 	// 表示可能的条件类型，unary, binary
# 	ConditionType string `json:"condition_type"`
# 	// 表示条件的操作符，比如大于，小于，等于, 如果是一元表达式，可能有time since
# 	Operator IOperator `json:"operator"`
# 	// 参与运算的因子
# 	Factors []IFactor `json:"factors"`
# }


class Condition:
    # todo 补充运算校验，添加因子加载, 运算执行逻辑

    def __init__(self, **data):
        self.condition_id = data.get("condition_id", None)
        self.start_time = data.get("start_time", None)
        self.operator = data.get("operator", None)
        if self.start_time is None or self.condition_id is None or self.operator is None:
            raise ValueError("start_time or condition_id is None")
        
        self.condition_type = data.get("condition_type", "binary")
        if self.condition_type == "unary":
            self._check_valid_operator()
        self.end_time = data.get("end_time", None)
        self.factors = data.get("factors", None)

    def _check_valid_operator(self):
        if self.operator not in ["eq", "ne", "gt", "lt", "ge", "le", "ta"]:
            raise ValueError(f"invalid operator: {self.operator}")
