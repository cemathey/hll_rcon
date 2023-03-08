import inspect
from itertools import cycle
from typing import Self

import trio
from loguru import logger

from async_hll_rcon import constants


class HllConnection:
    """Represents an underlying low level socket connection to the game server and returns raw results"""

    def __init__(
        self,
        ip_addr: str,
        port: int,
        password: str,
        receive_timeout: int = constants.TCP_TIMEOUT_READ,
        tcp_timeout: int = constants.TCP_TIMEOUT,
    ) -> None:
        self.ip_addr = ip_addr
        self.port = int(port)
        self.password = password
        self.receive_timeout = receive_timeout
        self.tcp_timeout = tcp_timeout
        self.xor_key: bytes
        self._connection: trio.SocketStream | None = None
        self.logged_in = False

    def _validate_timeout(self, value: float) -> None:
        """Check that value is float like and positive for TCP timeouts"""
        try:
            float(value)
        except ValueError:
            raise ValueError(
                f"`receive_timeout={value}` must be a float or castable to a float"
            )

        if value < 0:
            raise ValueError(f"`receive_timeout={value}` must be >= 0")

    @property
    def receive_timeout(self) -> float:
        return self._receive_timeout

    @receive_timeout.setter
    def receive_timeout(self, value: float) -> None:
        self._validate_timeout(value)

        self._receive_timeout = value

    @property
    def tcp_timeout(self) -> float:
        return self._tcp_timeout

    @tcp_timeout.setter
    def tcp_timeout(self, value: float) -> None:
        self._validate_timeout(value)

        self._tcp_timeout = value

    @property
    def connection(self) -> trio.SocketStream:
        """Safety check to make sure an unconnected instance isn't used"""
        if self._connection is not None:
            return self._connection
        else:
            raise ValueError("Socket connection to the game server not established.")

    @staticmethod
    def xor_encode(
        message: str | bytes, xor_key: bytes, encoding: str = "utf-8"
    ) -> bytes:
        """XOR encrypt the given message with the given XOR key"""
        if isinstance(message, str):
            message = message.encode(encoding=encoding)

        return bytes(
            [
                message_char ^ xor_char
                for message_char, xor_char in zip(message, cycle(xor_key))
            ]
        )

    @staticmethod
    def xor_decode(cipher_text: str | bytes, xor_key: bytes) -> str:
        """XOR decrypt the given cipher text with the given XOR key"""
        return HllConnection.xor_encode(cipher_text, xor_key).decode("utf-8")

    @classmethod
    async def setup(
        cls,
        ip_addr: str,
        port: int,
        password: str,
        receive_timeout: int,
        tcp_timeout: int,
    ) -> Self:
        """Create and return an instance after it has connected to the game server"""
        instance = HllConnection(ip_addr, port, password, receive_timeout, tcp_timeout)
        await instance.connect()
        return instance

    async def connect(self):
        """Connect to and log into the game server"""
        await self._connect()
        await self.login()

    async def _connect(self):
        """Open a socket to the game server and retrieve the XOR key"""
        with trio.fail_after(self.tcp_timeout):
            self._connection = await trio.open_tcp_stream(self.ip_addr, self.port)

        # The very first thing the game server will return is the XOR key that all
        # subsequent requests require for encoding/decoding
        with trio.fail_after(self.tcp_timeout):
            self.xor_key = await self._receive_from_game_server()

    async def _receive_from_game_server(
        self, max_bytes: int | None = constants.CHUNK_SIZE
    ) -> bytes:
        """Accumulate chunks of bytes from the game server and return them

        The game server does not indicate end of blocks of data in any way and does not
        send the empty (b"") value trio would need to iterate over the connection. Instead
        we repeatedly try to read from the socket until we time out at self.receive_timeout
        seconds and then return all the accumulated data
        """

        # TODO: We really need a better way to do this to account for slower connections
        # without also blocking when there's no content to receive
        buffer = bytearray()
        while True:
            try:
                with trio.fail_after(self.receive_timeout):
                    buffer += await self.connection.receive_some(max_bytes)
            except trio.TooSlowError:
                break

        return bytes(buffer)

    async def _send_to_game_server(self, content: str):
        """XOR the content and send to the game server, returning the game server response"""
        xored_content = HllConnection.xor_encode(content, self.xor_key)

        with trio.fail_after(self.tcp_timeout):
            logger.debug(f"sending content={content}")
            await self.connection.send_all(xored_content)
            result = await self._receive_from_game_server()

        logger.warning(f"received {len(result)=} bytes")

        return HllConnection.xor_decode(result, self.xor_key)

    async def login(self):
        """Log into the game server"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Login {self.password}"
        return await self._send_to_game_server(content)

    async def get_server_name(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Name"
        return await self._send_to_game_server(content)

    async def get_current_max_player_slots(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Slots"
        return await self._send_to_game_server(content)

    async def get_gamestate(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get GameState"
        return await self._send_to_game_server(content)

    async def get_max_queue_size(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get MaxQueuedPlayers"
        return await self._send_to_game_server(content)

    async def set_max_queue_size(self, size: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetMaxQueuedPlayers {size}"
        return await self._send_to_game_server(content)

    async def get_num_vip_slots(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get NumVipSlots"
        return await self._send_to_game_server(content)

    async def set_num_vip_slots(self, amount: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({amount=})"  # type: ignore
        )
        content = f"SetNumVipSlots {amount}"
        return await self._send_to_game_server(content)

    async def set_welcome_message(self, message: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({message=})"  # type: ignore
        )
        content = f"Say {message}"
        return await self._send_to_game_server(content)

    async def set_broadcast_message(self, message: str | None):
        # TODO: Failing with a blank message?
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({message=})"  # type: ignore
        )
        if message:
            content = f"Broadcast {message}"
        else:
            content = f"Broadcast "

        return await self._send_to_game_server(content)

    async def reset_broadcast_message(self):
        return await self.set_broadcast_message(None)

    async def get_game_logs(self, minutes: int, filter: str | None = None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({minutes=}, {filter=})"  # type: ignore
        )
        if filter is None:
            filter = ""

        content = f'ShowLog {minutes} "{filter}"'
        return await self._send_to_game_server(content)

    async def get_current_map(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Map"
        return await self._send_to_game_server(content)

    async def get_available_maps(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get MapsForRotation"
        return await self._send_to_game_server(content)

    async def get_map_rotation(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"RotList"
        return await self._send_to_game_server(content)

    async def add_map_to_rotation(
        self,
        name: str,
        after_map_name: str | None = None,
        after_map_ordinal: int | None = None,
    ):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"RotAdd {name} {after_map_name or ''} {after_map_ordinal or ''}"
        return await self._send_to_game_server(content)

    async def remove_map_from_rotation(self, name: str, ordinal: int | None = 1):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"RotDel {name} {ordinal or ''}"
        return await self._send_to_game_server(content)

    async def set_current_map(self, name: str, ordinal: int | None = 1):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Map {name} {ordinal or ''}"
        return await self._send_to_game_server(content)

    async def get_players(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Players"
        return await self._send_to_game_server(content)

    async def get_player_steam_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get PlayerIds"
        return await self._send_to_game_server(content)

    async def get_admin_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AdminIds"
        return await self._send_to_game_server(content)

    async def get_admin_groups(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AdminGroups"
        return await self._send_to_game_server(content)

    async def add_admin(self, steam_id_64: str, role: str, name: str | None = None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"AdminAdd {steam_id_64} {role} {name or ''}"
        return await self._send_to_game_server(content)

    async def remove_admin(self, steam_id_64: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"AdminDel {steam_id_64}"
        return await self._send_to_game_server(content)

    async def get_vip_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VipIds"
        return await self._send_to_game_server(content)

    async def get_player_info(self, player_name: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"PlayerInfo {player_name}"
        return await self._send_to_game_server(content)

    async def add_vip(self, steam_id_64: str, name: str | None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"VipAdd {steam_id_64} {name}"
        return await self._send_to_game_server(content)

    async def remove_vip(self, steam_id_64: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"VipDel {steam_id_64}"
        return await self._send_to_game_server(content)

    async def get_temp_bans(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get TempBans"
        return await self._send_to_game_server(content)

    async def get_permanent_bans(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get PermaBans"
        return await self._send_to_game_server(content)

    async def message_player(
        self,
        message: str,
        steam_id_64: str | None = None,
        player_name: str | None = None,
    ):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f'Message "{steam_id_64 or player_name}" "{message}"'
        return await self._send_to_game_server(content)

    async def punish_player(self, player_name: str, reason: str | None = None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Punish {player_name} {reason}"
        return await self._send_to_game_server(content)

    async def switch_player_on_death(self, player_name: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SwitchTeamOnDeath {player_name}"
        return await self._send_to_game_server(content)

    async def switch_player_now(self, player_name: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SwitchTeamNow {player_name}"
        return await self._send_to_game_server(content)

    async def kick_player(self, player_name: str, reason: str | None = None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Kick {player_name} {reason}"
        return await self._send_to_game_server(content)

    async def temp_ban_player(
        self,
        steam_id_64: str | None = None,
        player_name: str | None = None,
        duration: int | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
    ):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )

        if duration is None:
            validated_duration = ""
        else:
            validated_duration = str(duration)

        if reason is None:
            reason = ""

        if by_admin_name is None:
            by_admin_name = ""

        content = f'TempBan "{steam_id_64 or player_name}" {validated_duration} "{reason}" "{by_admin_name}"'
        return await self._send_to_game_server(content)

    async def perma_ban_player(
        self,
        steam_id_64: str | None = None,
        player_name: str | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
    ):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )

        if reason is None:
            reason = ""

        if by_admin_name is None:
            by_admin_name = ""

        content = (
            f'PermaBan "{steam_id_64 or player_name}" "{reason}" "{by_admin_name}"'
        )
        return await self._send_to_game_server(content)

    async def remove_temp_ban(self, ban_log: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"PardonTempBan {ban_log}"
        return await self._send_to_game_server(content)

    async def remove_perma_ban(self, ban_log: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"PardonPermaBan {ban_log}"
        return await self._send_to_game_server(content)

    async def get_idle_kick_time(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Idletime"
        return await self._send_to_game_server(content)

    async def set_idle_kick_time(self, threshold_minutes: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetKickIdleTime {threshold_minutes}"
        return await self._send_to_game_server(content)

    async def get_high_ping_limit(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get HighPing"
        return await self._send_to_game_server(content)

    async def set_high_ping_limit(self, threshold: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetHighPing {threshold}"
        return await self._send_to_game_server(content)

    async def disable_high_ping_limit(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        return await self.set_high_ping_limit(0)

    async def get_team_switch_cooldown(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get TeamSwitchCooldown"
        return await self._send_to_game_server(content)

    async def set_team_switch_cooldown(self, cooldown: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetTeamSwitchCooldown {cooldown}"
        return await self._send_to_game_server(content)

    async def get_auto_balance_enabled(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"AutoBalanceEnabled"
        return await self._send_to_game_server(content)

    async def enable_auto_balance(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutobalanceEnabled {constants.HLL_BOOL_ENABLED}"
        return await self._send_to_game_server(content)

    async def disable_auto_balance(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutobalanceEnabled {constants.HLL_BOOL_DISABLED}"
        return await self._send_to_game_server(content)

    async def get_auto_balance_threshold(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AutoBalanceThreshold"
        return await self._send_to_game_server(content)

    async def set_auto_balance_threshold(self, threshold: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutoBalanceThreshold {threshold}"
        return await self._send_to_game_server(content)

    async def get_vote_kick_enabled(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VoteKickEnabled"
        return await self._send_to_game_server(content)

    async def enable_vote_kick(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickEnabled  {constants.HLL_BOOL_ENABLED}"
        return await self._send_to_game_server(content)

    async def disable_vote_kick(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickEnabled  {constants.HLL_BOOL_DISABLED}"
        return await self._send_to_game_server(content)

    async def get_vote_kick_thresholds(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VoteKickThreshold"
        return await self._send_to_game_server(content)

    async def set_vote_kick_threshold(self, threshold_pairs: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickThreshold {threshold_pairs}"
        return await self._send_to_game_server(content)

    async def reset_vote_kick_threshold(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"ResetVoteKickThreshold"
        return await self._send_to_game_server(content)

    async def get_censored_words(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Profanity"
        return await self._send_to_game_server(content)

    async def censor_words(self, words: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"BanProfanity {words}"
        return await self._send_to_game_server(content)

    async def uncensor_words(self, words: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"UnbanProfanity {words}"
        return await self._send_to_game_server(content)
