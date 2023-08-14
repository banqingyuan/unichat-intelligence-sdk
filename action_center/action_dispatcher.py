import threading

import grpc
import logging
from common_py.client.rpc.gen.ai_message import ai_message_pb2_grpc, ai_message_pb2

from action_center.registration_form import action_form
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


def notify_client(AID: str, UID: str, message: str):
    with grpc.insecure_channel("unichat-server-dev:50051") as channel:
        stub = ai_message_pb2_grpc.AIMessageStub(channel)
        request = ai_message_pb2.AIActionNotificationRequest(
            AID=AID,
            UID=UID,
            Message=message,
        )
        response = stub.AIActionNotification(request)
        logger.info(f"notify_client AID: {AID}, UID: {UID}, request {message} response: {response}")
        return response