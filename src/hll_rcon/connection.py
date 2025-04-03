from loguru import logger
import socket
import pydantic
import struct
from itertools import cycle, count
import base64
from hll_rcon.types.constants import (
    RESPONSE_HEADER_SIZE,
    HEADER_BIT_FORMAT,
    RCON_PROTOCOL_VERSION,
)
from hll_rcon.types.constants import RconResponseStatusCode
from hll_rcon.types.server_requests import RconRequest, ContentBody
from hll_rcon.types.server_responses import RconResponse
from hll_rcon.exceptions import HLLAuthError, HLLBadCommand, HLLGameServerError


class HLLConnection:
    """Manages a single TCP socket connection over the RCON V2 protocol"""

    # Keep track of each individual request made so when the protocol
    # is updated we can make concurrent requests easier
    __request_id = count(start=1)

    # The game server will send an 8 byte little endian response header

    def __init__(
        self,
        protocol_version: int = RCON_PROTOCOL_VERSION,
        timeout: float | None = None,
    ) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(timeout)
        self.protocol_version: int = protocol_version
        self.xor_key: bytes | None = None
        self.auth_token: str | None = None
        # V2 currently returns a XOR key after the initial request for V1 compatibility
        # and we need to keep track so we can dump those initial 4 bytes
        self.v1_xor_key_received: bool = False
        self.id = next(self.__request_id)

    def _xor_encode(
        self, message: str | bytes | bytearray, encoding: str = "utf-8"
    ) -> bytes:
        """XOR encrypt the given message with the given XOR key"""

        # The initial request to the server isn't XOR encoded because
        # we don't have the key yet
        if not self.xor_key:
            if isinstance(message, str):
                return message.encode()
            return message

        if isinstance(message, str):
            message = message.encode(encoding=encoding)

        return bytes(
            [
                message_char ^ xor_char
                for message_char, xor_char in zip(message, cycle(self.xor_key))
            ]
        )

    def _xor_decode(self, cipher_text: str | bytes | bytearray) -> str:
        """XOR decrypt the given cipher text with the given XOR key"""
        return self._xor_encode(cipher_text).decode("utf-8")

    def encode(self, request: RconRequest) -> bytes:
        """Serialize and XOR encode the requested command"""
        # TODO: They (should) add a header to requests and not just responses
        # and we will add it here
        body = request.model_dump_json(by_alias=True)
        return self._xor_encode(body)

    def request(self, command: str, body: ContentBody | str | None) -> RconResponse:
        """Make a request to the game server"""
        if self.auth_token is None:
            raise HLLAuthError

        return self.send(RconRequest(command=command, body=body, auth=self.auth_token))

    def send(self, request: RconRequest) -> RconResponse:
        """Encode/send the request to the game server"""

        logger.debug(
            f"sending request={request.model_dump_json()}",
        )
        payload: bytes = self.encode(request)
        self.socket.sendall(payload)

        # The game server still sends the V1 XOR key which needs to be ignored
        if not self.v1_xor_key_received:
            _ = self.socket.recv(4)
            self.v1_xor_key_received = True

        # The response header is always a fixed 8 bytes
        header = bytearray()
        while len(header) < RESPONSE_HEADER_SIZE:
            chunk = self.socket.recv(RESPONSE_HEADER_SIZE - len(header))
            header.extend(chunk)

        # TODO: Once the protocol supports request IDs, use the response ID to match request -> response
        response_id, content_length = struct.unpack(HEADER_BIT_FORMAT, header)
        logger.debug(f"{response_id=} {content_length=}")

        # Receive content_length bytes
        raw_content = bytearray()
        while len(raw_content) < content_length:
            chunk = self.socket.recv(content_length - len(raw_content))
            raw_content.extend(chunk)

        content = self._xor_decode(raw_content)
        logger.debug(f"received: {content}")
        # Validate the response format or bubble up a ValidationError
        response = RconResponse.model_validate_json(content)

        match response.status_code:
            case RconResponseStatusCode.BAD_REQUEST:
                raise HLLBadCommand(response.status_msg)
            case RconResponseStatusCode.UNAUTHORIZED:
                raise HLLAuthError(response.status_msg)
            case RconResponseStatusCode.BAD_REQUEST:
                raise HLLGameServerError(response.status_msg)
            case _:
                # RconResponseStatusCode.OK
                return response

    def connect(self, host: str, port: int, password: str) -> None:
        """Connect to the game server; authenticate and set the XOR key for future requests"""
        self.socket.connect((host, int(port)))

        # Once a socket connection is open the game server will return a XOR key
        command = RconRequest(command="ServerConnect", auth="", body=None)
        response = self.send(command)
        self.xor_key = base64.b64decode(response.body)
        logger.debug(f"XOR key={self.xor_key}")

        # Once we login the game server returns an auth token used on every subsequent request
        command = RconRequest(command="Login", auth="", body=password)
        response = self.send(command)
        logger.debug(f"{response=}")
        self.auth_token = response.body

    def close(self) -> None:
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            logger.debug("Unable to send socket shutdown")
        finally:
            self.socket.close()
