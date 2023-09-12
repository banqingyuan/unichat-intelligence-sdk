# from pydantic import BaseModel
#
#
# class Factor(BaseModel):
#     factor_id: int
#     factor_type: str        # 类型，比如，int, string, bool, time
#     factor_value: str
#
#     entity: str         # 枚举值，业务实体，比如, room, user,
#     element: str     # 实体属性，比如，room_id, user_id
#
#     def load_factor(self) -> str:
#         """
#         从数据源中加载因子的值
#         :return:
#         """
#         pass
#
#     def _load_datasource(self):
#         """
#         加载数据源
#         :return:
#         """
#         pass
