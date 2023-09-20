import logging

import grpc
from common_py.client.rpc.gen.ai_message import ai_message_pb2_grpc, ai_message_pb2
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


def if_user_energy_used_up(ai_service_channel_name: str, UID: str) -> bool:
    """
    判断用户体力是否用完
    :return: bool
    """

    """
    message GetUserBalanceRequest {
        string UID = 1;
    }
    
    message GetUserBalanceResponse {
        StatusCodeEnum StatusCode  = 1;
        string Message = 2;
        int32 Balance = 3;
    }
    """
    with grpc.insecure_channel(ai_service_channel_name) as channel:
        stub = ai_message_pb2_grpc.AIMessageStub(channel)
        request = ai_message_pb2.GetUserBalanceRequest(
            UID=UID,
        )
        response = stub.GetUserBalance(request)
        logger.debug(f"if_user_energy_used_up response: {response}")
        if response.StatusCode == 0:
            if response.Balance > 0:
                return False
            else:
                return True
        else:
            raise Exception(f"if_user_energy_used_up error: {response.Message}")


Energy_Cost_Type_AI_Audio = "AI_Audio"
Energy_Cost_Type_User_Audio = "User_Audio"


def record_user_energy_cost(UUID: str, UID: str, AID: str, typ: str, quantity: int, remark: str, ai_service_channel_name: str) -> int:

    """
    return energy cost
    message AIConsumeRequest {
        // unique id of this consumption.
        string UUID = 1;
        // UID is the user uid who consume AI energy.
        string UID = 2;
        string AID = 3;
        string Type = 4; // "AI_Audio" or "User_Audio"
        int32 Quantity = 5;
        string Remark = 6;
    }

    message AIConsumeResponse {
        StatusCodeEnum    StatusCode  = 1;
        string            Message = 2;
        int32             EnergyCost = 3;
    }
    """

    with grpc.insecure_channel(ai_service_channel_name) as channel:
        stub = ai_message_pb2_grpc.AIMessageStub(channel)
        request = ai_message_pb2.AIConsumeRequest(
            UUID=UUID,
            UID=UID,
            AID=AID,
            Type=typ,
            Quantity=quantity,
            Remark=remark,
        )
        response = stub.AIConsume(request)
        logger.debug(f"record_user_energy_cost response: {response}")
        if response.StatusCode == 0:
            return response.EnergyCost
        else:
            raise Exception(f"record_user_energy_cost error: {response.Message}")


def energy_record_UUID(UUID: str, cost_type: str) -> str:
    """
    根据UUID和cost_type生成唯一的UUID
    :param UUID:
    :param cost_type:
    :return:
    """
    return f"{UUID}_{cost_type}"
