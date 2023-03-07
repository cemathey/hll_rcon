import inspect
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from itertools import cycle
from typing import AsyncGenerator, Generator, Iterable, Self

import trio
from dateutil import parser
from loguru import logger

from async_hll_rcon import constants
from async_hll_rcon.typedefs import (
    FAIL,
    FAIL_MAP_REMOVAL,
    HLL_BOOL_DISABLED,
    HLL_BOOL_ENABLED,
    SUCCESS,
    VALID_ADMIN_ROLES,
    Amount,
    AutoBalanceEnabled,
    AutoBalanceThreshold,
    BanLogType,
    ChatLogType,
    ConnectLogType,
    DisconnectLogType,
    HighPingLimit,
    IdleKickTime,
    IntegerGreaterOrEqualToOne,
    InvalidTempBanType,
    KickLogType,
    KillLogType,
    LogTimeStamp,
    MatchEndLogType,
    MatchStartLogType,
    PermanentBanType,
    PlayerInfo,
    Score,
    TeamKillLogType,
    TeamSwitchCoolDown,
    TeamSwitchLogType,
    TemporaryBanType,
    VoteKickEnabled,
    VoteKickThreshold,
)

TCP_TIMEOUT = 1


class HllConnection:
    """Represents an underlying low level socket connection to the game server and returns raw results"""

    def __init__(self, ip_addr: str, port: int, password: str) -> None:
        self.ip_addr = ip_addr
        self.port = int(port)
        self.password = password
        self._xor_key: bytes
        self._connection: trio.SocketStream | None = None
        self.logged_in = False

    @classmethod
    def _xor_encode(
        cls, message: str | bytes, xor_key: bytes, encoding: str = "utf-8"
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

    @classmethod
    def _xor_decode(cls, cipher_text: str | bytes, xor_key: bytes) -> str:
        """XOR decrypt the given cipher text with the given XOR key"""
        return cls._xor_encode(cipher_text, xor_key).decode("utf-8")

    @classmethod
    async def setup(cls, ip_addr: str, port: int, password: str) -> Self:
        """Create and return an instance after it has connected to the game server"""
        instance = HllConnection(ip_addr, port, password)
        await instance.connect()
        return instance

    @property
    def xor_key(self):
        return self._xor_key

    @property
    def connection(self) -> trio.SocketStream:
        if self._connection is not None:
            return self._connection
        else:
            raise ValueError("Invalid Connection")

    async def _connect(self):
        with trio.move_on_after(TCP_TIMEOUT):
            logger.debug(f"{id(self)} Opening socket")
            self._connection = await trio.open_tcp_stream(self.ip_addr, self.port)
            logger.debug(f"{id(self)} Socket open")

    async def connect(self):
        while self._connection is None:
            # TODO: This is probably dumb and connection raises a ValueError if it
            # isn't connected, should probably catch that and try up to a user
            # configurable number of retries or timeout or both to re-connect this socket
            # before failing
            await self._connect()

        # The very first thing the game server will return is the XOR key that all
        # subsequent requests require
        with trio.move_on_after(TCP_TIMEOUT):
            logger.debug(f"{id(self)} Getting XOR key in {id(self)}")
            self._xor_key = await self.connection.receive_some()
            logger.debug(f"{id(self)} Got XOR key={self.xor_key} in {id(self)}")

        with trio.move_on_after(TCP_TIMEOUT):
            logger.debug(f"{id(self)} Logging in")
            await self.login()
            # logger.debug(self.connection)
            logger.debug(f"{id(self)} Logged in")

    async def _send(self, content: str):
        """XOR the content and sendd to the game server, returning the game server response"""
        logger.debug(f"{id(self)} Sending {content=} to the game server")
        xored_content = HllConnection._xor_encode(content, self.xor_key)

        results: list[bytes] = []

        with trio.move_on_after(TCP_TIMEOUT) as cancel_scope:
            logger.debug(f"sending content")
            await self.connection.send_all(xored_content)
            logger.debug(f"content sent after")

        logger.debug(f"send: {cancel_scope.cancelled_caught=}")

        with trio.move_on_after(TCP_TIMEOUT) as cancel_scope:
            async for buffer in self.connection:
                logger.debug(f"{len(buffer)=}")
                results.append(buffer)
                logger.debug(f"{len(results)=}")

            logger.debug(f"receive: {cancel_scope.cancelled_caught=}")

            if cancel_scope.cancelled_caught:
                raise ValueError(f"timed out while receiving response")

        combined_results = b"".join(results)
        logger.debug(f"{HllConnection._xor_decode(combined_results, self.xor_key)}")
        return HllConnection._xor_decode(combined_results, self.xor_key)

    async def login(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Login {self.password}"
        return await self._send(content)

    async def get_server_name(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Name"
        return await self._send(content)

    async def get_current_max_player_slots(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Slots"
        return await self._send(content)

    async def get_gamestate(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get GameState"
        return await self._send(content)

    async def get_max_queue_size(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get MaxQueuedPlayers"
        return await self._send(content)

    async def set_max_queue_size(self, size: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetMaxQueuedPlayers {size}"
        return await self._send(content)

    async def get_num_vip_slots(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get NumVipSlots"
        return await self._send(content)

    async def set_num_vip_slots(self, amount: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({amount=})"  # type: ignore
        )
        content = f"SetNumVipSlots {amount}"
        return await self._send(content)

    async def set_welcome_message(self, message: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({message=})"  # type: ignore
        )
        content = f"Say {message}"
        return await self._send(content)

    async def set_broadcast_message(self, message: str | None):
        # TODO: Failing with a blank message?
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({message=})"  # type: ignore
        )
        if message:
            content = f"Broadcast {message}"
        else:
            content = f"Broadcast "

        return await self._send(content)

    async def reset_broadcast_message(self):
        return await self.set_broadcast_message(None)

    async def get_game_logs(self, minutes: int, filter: str | None = None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({minutes=}, {filter=})"  # type: ignore
        )
        if filter is None:
            filter = ""

        content = f'ShowLog {minutes} "{filter}"'
        return await self._send(content)

    async def get_current_map(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Map"
        return await self._send(content)

    async def get_available_maps(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get MapsForRotation"
        return await self._send(content)

    async def get_map_rotation(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"RotList"
        return await self._send(content)

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
        return await self._send(content)

    async def remove_map_from_rotation(self, name: str, ordinal: int | None = 1):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"RotDel {name} {ordinal or ''}"
        return await self._send(content)

    async def set_current_map(self, name: str, ordinal: int | None = 1):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Map {name} {ordinal or ''}"
        return await self._send(content)

    async def get_players(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Players"
        return await self._send(content)

    async def get_player_steam_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get PlayerIds"
        return await self._send(content)

    async def get_admin_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AdminIds"
        return await self._send(content)

    async def get_admin_groups(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AdminGroups"
        return await self._send(content)

    async def add_admin(self, steam_id_64: str, role: str, name: str | None = None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"AdminAdd {steam_id_64} {role} {name or ''}"
        return await self._send(content)

    async def remove_admin(self, steam_id_64: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"AdminDel {steam_id_64}"
        return await self._send(content)

    async def get_vip_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VipIds"
        return await self._send(content)

    async def get_player_info(self, player_name: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"PlayerInfo {player_name}"
        return await self._send(content)

    async def add_vip(self, steam_id_64: str, name: str | None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"VipAdd {steam_id_64} {name}"
        return await self._send(content)

    async def remove_vip(self, steam_id_64: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"VipDel {steam_id_64}"
        return await self._send(content)

    async def get_temp_bans(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get TempBans"
        return await self._send(content)

    async def get_permanent_bans(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get PermaBans"
        return await self._send(content)

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
        return await self._send(content)

    async def punish_player(self, player_name: str, reason: str | None = None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Punish {player_name} {reason}"
        return await self._send(content)

    async def switch_player_on_death(self, player_name: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SwitchTeamOnDeath {player_name}"
        return await self._send(content)

    async def switch_player_now(self, player_name: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SwitchTeamNow {player_name}"
        return await self._send(content)

    async def kick_player(self, player_name: str, reason: str | None = None):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Kick {player_name} {reason}"
        return await self._send(content)

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
        return await self._send(content)

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
        return await self._send(content)

    async def remove_temp_ban(self, ban_log: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"PardonTempBan {ban_log}"
        return await self._send(content)

    async def remove_perma_ban(self, ban_log: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"PardonPermaBan {ban_log}"
        return await self._send(content)

    async def get_idle_kick_time(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Idletime"
        return await self._send(content)

    async def set_idle_kick_time(self, threshold_minutes: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetKickIdleTime {threshold_minutes}"
        return await self._send(content)

    async def get_high_ping_limit(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get HighPing"
        return await self._send(content)

    async def set_high_ping_limit(self, threshold: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetHighPing {threshold}"
        return await self._send(content)

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
        return await self._send(content)

    async def set_team_switch_cooldown(self, cooldown: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetTeamSwitchCooldown {cooldown}"
        return await self._send(content)

    async def get_auto_balance_enabled(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"AutoBalanceEnabled"
        return await self._send(content)

    async def enable_auto_balance(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutobalanceEnabled {HLL_BOOL_ENABLED}"
        return await self._send(content)

    async def disable_auto_balance(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutobalanceEnabled {HLL_BOOL_DISABLED}"
        return await self._send(content)

    async def get_auto_balance_threshold(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AutoBalanceThreshold"
        return await self._send(content)

    async def set_auto_balance_threshold(self, threshold: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutoBalanceThreshold {threshold}"
        return await self._send(content)

    async def get_vote_kick_enabled(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VoteKickEnabled"
        return await self._send(content)

    async def enable_vote_kick(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickEnabled  {HLL_BOOL_ENABLED}"
        return await self._send(content)

    async def disable_vote_kick(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickEnabled  {HLL_BOOL_DISABLED}"
        return await self._send(content)

    async def get_vote_kick_thresholds(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VoteKickThreshold"
        return await self._send(content)

    async def set_vote_kick_threshold(self, threshold_pairs: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickThreshold {threshold_pairs}"
        return await self._send(content)

    async def reset_vote_kick_threshold(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"ResetVoteKickThreshold"
        return await self._send(content)

    async def get_censored_words(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Profanity"
        return await self._send(content)

    async def censor_words(self, words: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"BanProfanity {words}"
        return await self._send(content)

    async def uncensor_words(self, words: str):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"UnbanProfanity {words}"
        return await self._send(content)


class AsyncRcon:
    """Represents a high level RCON connection to the game server and returns processed results"""

    _temp_ban_log_pattern = re.compile(
        r"(\d{17}) :(?: nickname \"(.*)\")? banned for (\d+) hours on ([\d]{4}.[\d]{2}.[\d]{2}-[\d]{2}.[\d]{2}.[\d]{2})(?: for \"(.*)\" by admin \"(.*)\")?",
        re.DOTALL,
    )

    _temp_ban_log_missing_steam_id_name_pattern = re.compile(
        r"(\d{17})? :(?: nickname \"(.*)\")? banned for (\d+) hours on (.*) for \"(.*)\" by admin \"(.*)\"",
        re.DOTALL,
    )

    _perma_ban_log_pattern = re.compile(
        r"(\d{17}) :(?: nickname \"(.*)\")? banned on ([\d]{4}.[\d]{2}.[\d]{2}-[\d]{2}.[\d]{2}.[\d]{2})(?: for \"(.*)\" by admin \"(.*)\")?"
    )

    _kill_teamkill_pattern = re.compile(
        r"(?:(KILL):|(TEAM KILL):) (.*)\((Allies|Axis)\/(\d{17})\) -> (.*)\((Allies|Axis)\/(\d{17})\) with (.*)"
    )

    _chat_pattern = re.compile(
        r"CHAT\[(Team|Unit)\]\[(.*)\((Allies|Axis)/(\d{17})\)\]: (.*)"
    )

    _connect_disconnect_pattern = re.compile(
        r"(?:(CONNECTED)|(DISCONNECTED)) (.+) \((\d{17})\)"
    )

    _teamswitch_pattern = re.compile(r"(TEAMSWITCH) (.*) \((.*) > (.*)\)")
    # _kick_ban_pattern = re.compile(
    #     r"(?:(KICK)|(BAN)): \[(.*)\] .*\[(KICKED|BANNED|PERMANENTLY|YOU|Host|Anti-Cheat) ([^\]]*)\n?(.*)(?:\])",
    # )
    _kick_ban_pattern = re.compile(
        r"(?:(KICK)|(BAN)): \[(.*)\] has been (?:kicked|banned)\. \[(.*)\n?(.*)\]",
    )
    _vote_kick_pattern = None
    _admin_cam_pattern = None
    _match_start_pattern = re.compile(r"MATCH START (.*) (WARFARE|OFFENSIVE)")
    _match_end_pattern = re.compile(
        r"MATCH ENDED `(.*) (WARFARE|OFFENSIVE)` ALLIED \((\d) - (\d)"
    )
    _message_player_pattern = None

    def __init__(
        self, ip_addr: str, port: str, password: str, connection_pool_size: int = 1
    ) -> None:
        self._ip_addr = ip_addr
        self._port = int(port)
        self._password = password
        self.connections: list[HllConnection] = []

        # TODO: Pydantic validation
        if connection_pool_size < 1:
            raise ValueError(f"connection_pool_size must be a positive integer")

        self.connection_pool_size = connection_pool_size
        self.connection_limit = trio.CapacityLimiter(connection_pool_size)

    async def setup(self):
        """Create `connection_pool_size` HllConnection instances"""

        async def _inner_setup():
            connection = await HllConnection.setup(
                self._ip_addr, self._port, self._password
            )
            logger.debug(
                f"Connection {_+1}/{self.connection_pool_size} {id(self)} opened"
            )
            self.connections.append(connection)

        async with trio.open_nursery() as nursery:
            for _ in range(self.connection_pool_size):
                logger.debug(f"Opening connection {_+1}/{self.connection_pool_size}")
                nursery.start_soon(_inner_setup)

    @asynccontextmanager
    async def _get_connection(self) -> AsyncGenerator[HllConnection, None]:
        async with self.connection_limit:
            # in theory we never need to check for a connection being unavailable
            # because trio.CapacityLimiter should handle this for us and block if
            # it needs to wait for another connection
            connection = self.connections.pop()
            yield connection
            self.connections.append(connection)

    @staticmethod
    def to_hll_list(items: Iterable[str], separator: str = ",") -> str:
        return separator.join(items)

    @staticmethod
    def from_hll_list(raw_list: str) -> list[str]:
        """Convert a game server tab delimited result string to a native list"""
        # raw_list = raw_list.strip()

        expected_length, *items = raw_list.split("\t")
        expected_length = int(expected_length)

        if len(items) != expected_length:
            logger.debug(f"{expected_length=}")
            logger.debug(f"{len(items)=}")
            logger.debug(f"{items=}")
            if len(items) > 0 and items[0] and not items[-1]:
                logger.debug(f"{items[:-1]=}")
                return items[:-1]
            raise ValueError("List does not match expected length")

        return items

    async def login(self):
        async with self._get_connection() as conn:
            result = await conn.login()
            logger.debug(f"{id(self)} login {result=}")

    async def get_server_name(self):
        async with self._get_connection() as conn:
            result = await conn.get_server_name()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_current_max_player_slots(self):
        async with self._get_connection() as conn:
            result = await conn.get_current_max_player_slots()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_gamestate(self):
        async with self._get_connection() as conn:
            result = await conn.get_gamestate()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_max_queue_size(self):
        async with self._get_connection() as conn:
            result = await conn.get_max_queue_size()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def set_max_queue_size(self, size: int) -> bool:
        async with self._get_connection() as conn:
            result = await conn.set_max_queue_size(size=size)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def get_num_vip_slots(self):
        async with self._get_connection() as conn:
            result = await conn.get_num_vip_slots()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def set_num_vip_slots(self, amount: int):
        try:
            args = Amount(amount=amount)
        except ValueError as e:
            logger.error(f"{amount=} must be a positive integer")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_num_vip_slots(args.amount)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def set_welcome_message(self, message: str):
        async with self._get_connection() as conn:
            result = await conn.set_welcome_message(message=message)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def set_broadcast_message(self, message: str | None):
        async with self._get_connection() as conn:
            result = await conn.set_broadcast_message(message=message)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def reset_broadcast_message(self):
        async with self._get_connection() as conn:
            result = await conn.reset_broadcast_message()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    @staticmethod
    def relative_time_to_timedelta(relative_time: str) -> timedelta:
        raw_time, unit = relative_time.split(maxsplit=1)

        match unit:
            case "hours":
                hours, minutes, seconds = raw_time.split(":")
                return timedelta(
                    hours=float(hours), minutes=float(minutes), seconds=float(seconds)
                )
            case "min":
                minutes, seconds = raw_time.split(":")
                return timedelta(minutes=float(minutes), seconds=float(seconds))
            case "sec":
                seconds = float(raw_time)
                return timedelta(seconds=seconds)
            case "ms":
                ms = float(raw_time)
                return timedelta(milliseconds=ms)
            case _:
                raise ValueError(f"Unable to parse relative time=`{relative_time}`")

    @staticmethod
    def absolute_time_to_datetime(absolute_time: str) -> datetime:
        # Game server time stamps are already UTC
        return datetime.utcfromtimestamp(float(absolute_time))

    @staticmethod
    def parse_game_log(
        raw_log: str, relative_time: str, absolute_time: str
    ) -> (
        KillLogType
        | TeamKillLogType
        | ChatLogType
        | ConnectLogType
        | DisconnectLogType
        | TeamSwitchLogType
        | KickLogType
        | BanLogType
        | MatchStartLogType
        | MatchEndLogType
        | None
    ):
        time = LogTimeStamp(
            absolute_timestamp=AsyncRcon.absolute_time_to_datetime(absolute_time),
            relative_timestamp=AsyncRcon.relative_time_to_timedelta(relative_time),
        )

        if raw_log.startswith("KILL") or raw_log.startswith("TEAM KILL"):
            if match := re.match(AsyncRcon._kill_teamkill_pattern, raw_log):
                (
                    kill,
                    team_kill,
                    player_name,
                    player_team,
                    steam_id_64,
                    victim_player_name,
                    victim_team,
                    victim_steam_id_64,
                    weapon,
                ) = match.groups()

                if kill:
                    return KillLogType(
                        steam_id_64=steam_id_64,
                        player_name=player_name,
                        player_team=player_team,
                        victim_steam_id_64=victim_steam_id_64,
                        victim_player_name=victim_player_name,
                        victim_team=victim_team,
                        weapon=weapon,
                        time=time,
                    )
                else:
                    return TeamKillLogType(
                        steam_id_64=steam_id_64,
                        player_name=player_name,
                        player_team=player_team,
                        victim_steam_id_64=victim_steam_id_64,
                        victim_player_name=victim_player_name,
                        victim_team=victim_team,
                        weapon=weapon,
                        time=time,
                    )

        elif raw_log.startswith("CHAT"):
            if match := re.match(AsyncRcon._chat_pattern, raw_log):
                scope, player_name, team, steam_id_64, content = match.groups()
                return ChatLogType(
                    steam_id_64=steam_id_64,
                    player_name=player_name,
                    player_team=team,
                    scope=scope,
                    content=content,
                    time=time,
                )
            else:
                ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("CONNECTED") or raw_log.startswith("DISCONNECTED"):
            if match := re.match(AsyncRcon._connect_disconnect_pattern, raw_log):
                logger.debug(f"{match.groups()=}")
                connected, disconnected, player_name, steam_id_64 = match.groups()
                if connected:
                    return ConnectLogType(
                        steam_id_64=steam_id_64, player_name=player_name, time=time
                    )
                else:
                    return DisconnectLogType(
                        steam_id_64=steam_id_64, player_name=player_name, time=time
                    )
            else:
                ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("TEAMSWITCH"):
            if match := re.match(AsyncRcon._teamswitch_pattern, raw_log):
                logger.debug(f"{match.groups()=}")
                action, player_name, from_team, to_team = match.groups()
                return TeamSwitchLogType(
                    player_name=player_name,
                    from_team=from_team,
                    to_team=to_team,
                    time=time,
                )
            else:
                ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("BAN") or raw_log.startswith("KICK"):
            if match := re.match(AsyncRcon._kick_ban_pattern, raw_log):
                logger.debug(f"{match.groups()=}")
                (
                    kick,
                    ban,
                    player_name,
                    raw_removal_type,
                    # duration,
                    removal_reason,
                ) = match.groups()

                removal_reason = removal_reason.strip()
                ban_duration = None

                if kick:
                    if raw_removal_type.startswith("YOU"):
                        removal_type = constants.IDLE_KICK
                    elif raw_removal_type.startswith("Host"):
                        removal_type = constants.HOST_CLOSED_CONNECTION_KICK
                    elif raw_removal_type.startswith("KICKED"):
                        removal_type = constants.TEAM_KILLING_KICK
                    else:
                        raise ValueError(f"invalid {raw_removal_type=}")

                    return KickLogType(
                        player_name=player_name, kick_type=removal_type, time=time
                    )
                else:
                    if duration_match := re.match(
                        r"BANNED FOR (\d+) HOURS", raw_removal_type
                    ):
                        ban_duration = int(duration_match.groups()[0])
                        ban_type = constants.TEMPORARY_BAN
                    else:
                        ban_type = constants.PERMANENT_BAN

                    return BanLogType(
                        player_name=player_name,
                        ban_type=ban_type,
                        ban_duration_hours=ban_duration,
                        reason=removal_reason,
                        time=time,
                    )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("MATCH"):
            if match := re.match(AsyncRcon._match_start_pattern, raw_log):
                logger.debug(f"match start {match.groups()=}")
                map_name, game_mode = match.groups()
                return MatchStartLogType(
                    map_name=map_name, game_mode=game_mode, time=time
                )
            elif match := re.match(AsyncRcon._match_end_pattern, raw_log):
                logger.debug(f"match end {match.groups()=}")
                map_name, game_mode, allied_score, axis_score = match.groups()
                return MatchEndLogType(
                    map_name=map_name,
                    game_mode=game_mode,
                    allied_score=int(allied_score),
                    axis_score=int(axis_score),
                    time=time,
                )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        else:
            logger.error(f"Unable to parse `{raw_log}`")
            raise ValueError(f"Unable to parse `{raw_log}`")

    # _log_split_pattern = re.compile(r"^(\[.+? \((\d+)\)\])", re.MULTILINE)
    _log_split_pattern = re.compile(r"^\[(.+)? \((\d+)\)\]", re.MULTILINE)

    @staticmethod
    def split_raw_log_lines(
        raw_logs: str,
    ) -> Generator[tuple[str, str, str], None, None]:
        """Split raw game server logs into the line, relative time and absolute UTC timestamp"""
        if raw_logs != "":
            logs = raw_logs.strip("\n")
            # logs = re.split(r"^(\[.+? \((\d+)\)\])", logs, flags=re.M)
            logs = re.split(AsyncRcon._log_split_pattern, logs)

            logs = zip(logs[1::3], logs[2::3], logs[3::3])
            for raw_relative_time, raw_timestamp, raw_log_line in logs:
                yield raw_log_line.strip(), raw_relative_time, raw_timestamp,

    async def get_game_logs(self, minutes: int, filter: str | None = None):
        async with self._get_connection() as conn:
            result = await conn.get_game_logs(minutes=minutes, filter=filter)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result == "EMPTY":
            return []
        else:
            logs = []
            for raw_log, relative_time, absolute_time in AsyncRcon.split_raw_log_lines(
                result
            ):
                logger.debug(f"{relative_time=} {absolute_time=} {raw_log=}")
                logs.append(
                    AsyncRcon.parse_game_log(raw_log, relative_time, absolute_time)
                )

        return logs

    async def get_current_map(self):
        async with self._get_connection() as conn:
            result = await conn.get_current_map()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_available_maps(self):
        async with self._get_connection() as conn:
            result = await conn.get_available_maps()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_map_rotation(self):
        async with self._get_connection() as conn:
            result = await conn.get_map_rotation()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def add_map_to_rotation(
        self,
        name: str,
        after_map_name: str | None = None,
        after_map_ordinal: int | None = None,
    ):
        async with self._get_connection() as conn:
            result = await conn.add_map_to_rotation(
                name=name,
                after_map_name=after_map_name,
                after_map_ordinal=after_map_ordinal,
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        # TODO: Flesh out the actual error messages it returns
        if result not in (SUCCESS, FAIL_MAP_REMOVAL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def remove_map_from_rotation(self, name: str, ordinal: int | None = 1):
        async with self._get_connection() as conn:
            result = await conn.remove_map_from_rotation(name=name, ordinal=ordinal)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL_MAP_REMOVAL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def set_current_map(self, name: str, ordinal: int | None = 1) -> bool:
        async with self._get_connection() as conn:
            result = await conn.set_current_map(name=name, ordinal=ordinal)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def get_players(self):
        async with self._get_connection() as conn:
            result = await conn.get_players()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_player_steam_ids(self):
        async with self._get_connection() as conn:
            result = await conn.get_player_steam_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_admin_ids(self):
        async with self._get_connection() as conn:
            result = await conn.get_admin_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_admin_groups(self) -> list[str]:
        async with self._get_connection() as conn:
            result = await conn.get_admin_groups()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            groups = AsyncRcon.from_hll_list(result)

            if not all(group in VALID_ADMIN_ROLES for group in groups):
                raise ValueError(f"Received an invalid response from the game server")

            return groups

    async def add_admin(
        self, steam_id_64: str, role: str, name: str | None = None
    ) -> bool:
        async with self._get_connection() as conn:
            result = await conn.add_admin(steam_id_64=steam_id_64, role=role, name=name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def remove_admin(self, steam_id_64: str):
        async with self._get_connection() as conn:
            result = await conn.remove_admin(steam_id_64=steam_id_64)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def get_vip_ids(self):
        async with self._get_connection() as conn:
            result = await conn.get_vip_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )
            return AsyncRcon.from_hll_list(result)

    @staticmethod
    def parse_player_info(raw_player_info: str) -> PlayerInfo:
        lines = raw_player_info.strip().split("\n")
        if len(lines) != 7:
            raise ValueError(
                f"Received an invalid or incomplete `PlayerInfo` from the game server"
            )

        _, player_name = lines[0].split("Name: ")
        _, steam_id_64 = lines[1].split("steamID64: ")
        _, raw_team = lines[2].split("Team: ")
        _, role = lines[3].split("Role: ")
        left, right = lines[4].split(" - ")
        _, kills = left.split("Kills: ")
        _, deaths = right.split("Deaths: ")
        _, raw_scores = lines[5].split("Score: ")
        _, level = lines[6].split("Level: ")

        if raw_team == "None":
            team = None
        else:
            team = raw_team

        scores: dict[str, int] = {}
        for raw_score in raw_scores.split(","):
            key, score = raw_score.split(maxsplit=1)
            scores[key] = int(score)

        processed_score = Score(
            kills=int(kills),
            deaths=int(deaths),
            combat=scores["C"],
            offensive=scores["O"],
            defensive=scores["D"],
            support=scores["S"],
        )

        return PlayerInfo(
            player_name=player_name,
            steam_id_64=steam_id_64,
            team=team,
            role=role,
            score=processed_score,
            level=int(level),
        )

    async def get_player_info(self, player_name: str):
        async with self._get_connection() as conn:
            result = await conn.get_player_info(player_name=player_name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        return result

    async def add_vip(self, steam_id_64: str, name: str | None):
        async with self._get_connection() as conn:
            result = await conn.add_vip(steam_id_64=steam_id_64, name=name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def remove_vip(self, steam_id_64: str):
        async with self._get_connection() as conn:
            result = await conn.remove_vip(steam_id_64=steam_id_64)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    @staticmethod
    def parse_ban_log_timestamp(raw_timestamp: str) -> datetime:
        _date, _time = raw_timestamp.split("-")
        _time = _time.replace(".", ":")

        return parser.parse(f"{_date} {_time}")

    @staticmethod
    def parse_temp_ban_log(raw_ban: str) -> TemporaryBanType | InvalidTempBanType:
        """Parse a raw HLL ban log into a TempBanType dataclass

        76561199023367826 : nickname "(WTH) Abu" banned for 2 hours on 2021.12.09-16.40.08 for "Being a troll" by admin "Some Admin Name"
        """
        # TODO: Account for any other optional fields
        if match := re.match(AsyncRcon._temp_ban_log_pattern, raw_ban):
            (
                steam_id_64,
                player_name,
                duration_hours,
                raw_timestamp,
                reason,
                admin,
            ) = match.groups()

            timestamp = AsyncRcon.parse_ban_log_timestamp(raw_timestamp)

            ban = TemporaryBanType(
                steam_id_64=steam_id_64,
                player_name=player_name,
                duration_hours=int(duration_hours),
                timestamp=timestamp,
                reason=reason,
                admin=admin,
            )
        elif match := re.match(
            AsyncRcon._temp_ban_log_missing_steam_id_name_pattern, raw_ban
        ):
            (
                steam_id_64,
                player_name,
                duration_hours,
                raw_timestamp,
                reason,
                admin,
            ) = match.groups()

            timestamp = AsyncRcon.parse_ban_log_timestamp(raw_timestamp)

            ban = InvalidTempBanType(
                steam_id_64=steam_id_64,
                player_name=player_name,
                duration_hours=int(duration_hours),
                timestamp=timestamp,
                reason=reason,
                admin=admin,
            )
        else:
            raise ValueError(f"Received invalid temp ban log: `{raw_ban}`")

        return ban

    @staticmethod
    def parse_perma_ban_log(raw_ban: str) -> PermanentBanType:
        """Parse a raw HLL ban log into a TempBanType dataclass

        76561197975123456 : nickname "Georgij Zhukov Sovie" banned on 2022.12.06-16.27.14 for "Racism" by admin "BLACKLIST: NoodleArms"
        """
        # TODO: Account for any other optional fields
        if match := re.match(AsyncRcon._perma_ban_log_pattern, raw_ban):
            (
                steam_id_64,
                player_name,
                raw_timestamp,
                reason,
                admin,
            ) = match.groups()

            timestamp = AsyncRcon.parse_ban_log_timestamp(raw_timestamp)

            ban = PermanentBanType(
                steam_id_64=steam_id_64,
                player_name=player_name,
                timestamp=timestamp,
                reason=reason,
                admin=admin,
            )
        else:
            raise ValueError(f"Received invalid perma ban log: `{raw_ban}`")

        return ban

    async def get_temp_bans(self) -> list[TemporaryBanType | InvalidTempBanType]:
        async with self._get_connection() as conn:
            result = await conn.get_temp_bans()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            raw_results = AsyncRcon.from_hll_list(result)

            return [
                AsyncRcon.parse_temp_ban_log(raw_ban)
                for raw_ban in raw_results
                if raw_ban
            ]

    async def get_permanent_bans(self) -> list[PermanentBanType]:
        async with self._get_connection() as conn:
            result = await conn.get_permanent_bans()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )
            raw_results = AsyncRcon.from_hll_list(result)
            return [
                AsyncRcon.parse_perma_ban_log(raw_ban)
                for raw_ban in raw_results
                if raw_ban
            ]

    async def message_player(
        self,
        message: str,
        steam_id_64: str | None = None,
        player_name: str | None = None,
    ):
        async with self._get_connection() as conn:
            result = await conn.message_player(
                message=message, steam_id_64=steam_id_64, player_name=player_name
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def punish_player(self, player_name: str, reason: str | None = None):
        async with self._get_connection() as conn:
            result = await conn.punish_player(player_name=player_name, reason=reason)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def switch_player_on_death(self, player_name: str):
        async with self._get_connection() as conn:
            result = await conn.switch_player_on_death(player_name=player_name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def switch_player_now(self, player_name: str):
        async with self._get_connection() as conn:
            result = await conn.switch_player_now(player_name=player_name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def kick_player(self, player_name: str, reason: str | None = None):
        async with self._get_connection() as conn:
            result = await conn.kick_player(player_name=player_name, reason=reason)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def temp_ban_player(
        self,
        steam_id_64: str | None = None,
        player_name: str | None = None,
        duration: int | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
    ):
        if steam_id_64 is None and player_name is None:
            raise ValueError(f"Must provide at least either a steam ID or player name")

        try:
            args = IntegerGreaterOrEqualToOne(value=duration)
        except ValueError:
            raise ValueError(f"`duration` must be an integer >= 1 or None")

        async with self._get_connection() as conn:
            result = await conn.temp_ban_player(
                steam_id_64=steam_id_64,
                player_name=player_name,
                duration=args.value,
                reason=reason,
                by_admin_name=by_admin_name,
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def perma_ban_player(
        self,
        steam_id_64: str | None = None,
        player_name: str | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
    ):
        if steam_id_64 is None and player_name is None:
            raise ValueError(f"Must provide at least either a steam ID or player name")

        async with self._get_connection() as conn:
            result = await conn.perma_ban_player(
                steam_id_64=steam_id_64,
                player_name=player_name,
                reason=reason,
                by_admin_name=by_admin_name,
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def remove_temp_ban(self, ban_log: str | TemporaryBanType):
        # TODO: Handle invalid ban types?
        # if isinstance(ban_log, InvalidTempBanType):
        #     raise ValueError(f"Can'")

        if isinstance(ban_log, str):
            self.parse_temp_ban_log(ban_log)
        else:
            ban_log = str(ban_log)

        async with self._get_connection() as conn:
            result = await conn.remove_temp_ban(ban_log=ban_log)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def remove_perma_ban(self, ban_log: str | PermanentBanType):
        # TODO: Handle invalid ban types?
        # if isinstance(ban_log, InvalidTempBanType):
        #     raise ValueError(f"Can'")

        if isinstance(ban_log, str):
            self.parse_perma_ban_log(ban_log)
        else:
            ban_log = str(ban_log)

        async with self._get_connection() as conn:
            result = await conn.remove_perma_ban(ban_log=ban_log)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def get_idle_kick_time(self) -> IdleKickTime:
        async with self._get_connection() as conn:
            result = await conn.get_idle_kick_time()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            return IdleKickTime(kick_time=result)

    async def set_idle_kick_time(self, threshold_minutes: int) -> bool:
        args = IdleKickTime(kick_time=threshold_minutes)

        async with self._get_connection() as conn:
            result = await conn.set_idle_kick_time(threshold_minutes=args.kick_time)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (SUCCESS, FAIL):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == SUCCESS

    async def get_high_ping_limit(self):
        async with self._get_connection() as conn:
            result = await conn.get_high_ping_limit()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = HighPingLimit(limit=result)
        except ValueError as e:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        return validated_result.limit

    async def set_high_ping_limit(self, threshold: int):
        try:
            args = HighPingLimit(limit=threshold)
        except ValueError as e:
            logger.error(f"{threshold=} must be an integer >= 0")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_high_ping_limit(threshold=args.limit)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def disable_high_ping_limit(self):
        async with self._get_connection() as conn:
            result = await conn.disable_high_ping_limit()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def get_team_switch_cooldown(self) -> int:
        async with self._get_connection() as conn:
            result = await conn.get_team_switch_cooldown()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = TeamSwitchCoolDown(cooldown=result)
        except ValueError as e:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        return validated_result.cooldown

    async def set_team_switch_cooldown(self, cooldown: int):
        try:
            args = TeamSwitchCoolDown(cooldown=cooldown)
        except ValueError as e:
            logger.error(f"{cooldown=} must be a positive integer")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_team_switch_cooldown(args.cooldown)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def get_auto_balance_enabled(self):
        async with self._get_connection() as conn:
            result = await conn.get_auto_balance_enabled()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = AutoBalanceEnabled(enabled=result)  # type: ignore
        except ValueError as e:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        return validated_result.enabled

    async def enable_auto_balance(self):
        async with self._get_connection() as conn:
            result = await conn.enable_auto_balance()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def disable_auto_balance(self):
        async with self._get_connection() as conn:
            result = await conn.disable_auto_balance()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def get_auto_balance_threshold(self):
        async with self._get_connection() as conn:
            result = await conn.get_auto_balance_threshold()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = AutoBalanceThreshold(threshold=result)  # type: ignore
        except ValueError as e:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        return validated_result.threshold

    async def set_auto_balance_threshold(self, threshold: int):
        try:
            args = AutoBalanceThreshold(threshold=threshold)
        except ValueError as e:
            logger.error(f"{threshold=} must be a positive integer")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_auto_balance_threshold(args.threshold)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def get_vote_kick_enabled(self):
        async with self._get_connection() as conn:
            result = await conn.get_vote_kick_enabled()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = VoteKickEnabled(enabled=result)  # type: ignore
        except ValueError as e:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        return validated_result.enabled

    async def enable_vote_kick(self):
        async with self._get_connection() as conn:
            result = await conn.enable_vote_kick()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def disable_vote_kick(self):
        async with self._get_connection() as conn:
            result = await conn.disable_vote_kick()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def get_vote_kick_thresholds(self) -> list[VoteKickThreshold]:
        async with self._get_connection() as conn:
            result = await conn.get_vote_kick_thresholds()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        def parse_vote_kick_threshold(raw_thresholds: str) -> list[VoteKickThreshold]:
            values = raw_thresholds.split(",")
            thresholds: list[VoteKickThreshold] = []
            for player, vote in zip(values[0::2], values[1::2]):
                thresholds.append(
                    VoteKickThreshold(player_count=player, votes_required=vote)  # type: ignore
                )

            return thresholds

        try:
            return parse_vote_kick_threshold(result)
        except ValueError:
            raise ValueError(f"Received an invalid response from the game server")

    @staticmethod
    def convert_vote_kick_thresholds(
        thresholds: Iterable[tuple[int, int]] | Iterable[VoteKickThreshold] | str
    ) -> str:
        if thresholds is None:
            raise ValueError(
                "Vote kick thresholds must be pairs in the form (player count, votes required)"
            )

        raw_thresholds: list[int] = []
        if isinstance(thresholds, str):
            if len(thresholds.split(",")) % 2 != 0:
                raise ValueError(
                    "Vote kick thresholds must be pairs in the form (player count, votes required), received incomplete pairs"
                )
            elif thresholds == "":
                raise ValueError(
                    "Vote kick thresholds must be pairs in the form (player count, votes required)"
                )
            return thresholds
        else:
            for item in thresholds:
                if isinstance(item, VoteKickThreshold):
                    raw_thresholds.append(item.player_count)
                    raw_thresholds.append(item.votes_required)
                elif isinstance(item, tuple):
                    player, count = item
                    raw_thresholds.append(player)
                    raw_thresholds.append(count)
                else:
                    raise ValueError(
                        f"Vote kick thresholds must be pairs in the form (player count, votes required), received {item=}"
                    )

        if len(raw_thresholds) % 2 != 0:
            raise ValueError(
                "Vote kick thresholds must be pairs in the form (player count, votes required)"
            )

        return ",".join(str(threshold) for threshold in raw_thresholds)

    async def set_vote_kick_threshold(
        self, thresholds: Iterable[tuple[int, int]] | Iterable[VoteKickThreshold] | str
    ):
        processed_thresholds = self.convert_vote_kick_thresholds(thresholds)
        async with self._get_connection() as conn:
            result = await conn.set_vote_kick_threshold(
                threshold_pairs=processed_thresholds
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def reset_vote_kick_threshold(self):
        async with self._get_connection() as conn:
            result = await conn.reset_vote_kick_threshold()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (SUCCESS, FAIL):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == SUCCESS

    async def get_censored_words(self):
        async with self._get_connection() as conn:
            result = await conn.get_censored_words()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )
            return AsyncRcon.from_hll_list(result)

    async def censor_words(self, words: Iterable[str]):
        raw_words = AsyncRcon.to_hll_list(words)
        async with self._get_connection() as conn:
            result = await conn.censor_words(words=raw_words)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        return result

    async def uncensor_words(self, words: Iterable[str]):
        raw_words = AsyncRcon.to_hll_list(words)
        async with self._get_connection() as conn:
            result = await conn.uncensor_words(words=raw_words)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        return result


class Tracer(trio.abc.Instrument):
    def before_run(self):
        print("!!! run started")

    def _print_with_task(self, msg, task):
        # repr(task) is perhaps more useful than task.name in general,
        # but in context of a tutorial the extra noise is unhelpful.
        print(f"{msg}: {task.name}")

    def task_spawned(self, task):
        self._print_with_task("### new task spawned", task)

    def task_scheduled(self, task):
        self._print_with_task("### task scheduled", task)

    def before_task_step(self, task):
        self._print_with_task(">>> about to run one step of task", task)

    def after_task_step(self, task):
        self._print_with_task("<<< task step finished", task)

    def task_exited(self, task):
        self._print_with_task("### task exited", task)

    def before_io_wait(self, timeout):
        if timeout:
            print(f"### waiting for I/O for up to {timeout} seconds")
        else:
            print("### doing a quick check for I/O")
        self._sleep_time = trio.current_time()

    def after_io_wait(self, timeout):
        duration = trio.current_time() - self._sleep_time
        print(f"### finished I/O check (took {duration} seconds)")

    def after_run(self):
        print("!!! run finished")


async def main():
    host, port, password = (
        os.getenv("RCON_HOST"),
        os.getenv("RCON_PORT"),
        os.getenv("RCON_PASSWORD"),
    )

    if not host or not port or not password:
        logger.error(f"RCON_HOST, RCON_PORT or RCON_PASSWORD not set")
        return

    rcon = AsyncRcon(host, port, password)
    await rcon.setup()
    async with trio.open_nursery() as nursery:
        pass
        # nursery.start_soon(rcon.get_num_vip_slots)
        # nursery.start_soon(rcon.get_max_queue_size)
        # nursery.start_soon(rcon.get_server_name)
        # nursery.start_soon(rcon.get_current_max_player_slots)
        # nursery.start_soon(rcon.get_gamestate)
        # nursery.start_soon(rcon.get_current_map)
        # nursery.start_soon(rcon.get_available_maps)
        # nursery.start_soon(rcon.get_map_rotation)
        # nursery.start_soon(rcon.get_players)
        # nursery.start_soon(rcon.get_player_steam_ids)
        # nursery.start_soon(rcon.get_admin_ids)
        # nursery.start_soon(rcon.get_admin_groups)
        # nursery.start_soon(rcon.get_temp_bans)

    logger.debug(f"===========================")
    bans = await rcon.get_permanent_bans()
    for b in bans:
        if b:
            print(b)

    logger.debug(f"===========================")
    # logger.debug(await rcon.get_admin_groups())
    # logger.debug(await rcon.remove_vip("76561198004895814"))
    # logger.debug(await rcon.add_vip("76561198004895814", "NoodleArms"))
    # logger.debug(await rcon.set_broadcast_message("Test"))
    # logger.debug(await rcon.reset_broadcast_message())
    # logger.debug(await rcon.get_high_ping_limit())
    # logger.debug(await rcon.disable_high_ping_limit())
    # logger.debug(await rcon.get_high_ping_limit())
    # logger.debug(await rcon.set_high_ping_limit(0))
    # logger.debug(await rcon.enable_auto_balance())
    # logger.debug(await rcon.get_auto_balance_threshold())
    # logger.debug(await rcon.set_auto_balance_threshold(5))
    # logger.debug(await rcon.get_auto_balance_threshold())
    # logger.debug(await rcon.set_auto_balance_threshold(1))
    # logger.debug(await rcon.get_auto_balance_threshold())
    # logger.debug(await rcon.get_vote_kick_enabled())
    # logger.debug(await rcon.enable_vote_kick())
    # logger.debug(await rcon.get_vote_kick_enabled())
    # logger.debug(await rcon.disable_vote_kick())
    # logger.debug(await rcon.get_vote_kick_enabled())
    # logger.debug(await rcon.get_censored_words())
    # logger.debug(await rcon.censor_words(words=["bad", "words"]))
    # logger.debug(await rcon.get_censored_words())
    # logger.debug(await rcon.uncensor_words(words=["bad", "words"]))
    # logger.debug(await rcon.get_censored_words())
    # logger.debug(await rcon.get_vote_kick_thresholds())
    # logger.debug(await rcon.set_vote_kick_threshold([(0, 1)]))
    # logger.debug(await rcon.get_vote_kick_thresholds())
    # logger.debug(await rcon.reset_vote_kick_threshold())
    # logger.debug(await rcon.get_vote_kick_thresholds())
    # logger.debug(await rcon.get_player_info("NoodleArms"))
    # logger.debug(await rcon.punish_player("NoodleArms", "Testing"))
    # logger.debug(await rcon.switch_player_on_death("NoodleArms"))
    # logger.debug(await rcon.kick_player("NoodleArms"))
    # logger.debug(await rcon.kick_player("NoodleArms", "Testing'"))
    # logger.debug(
    #     await rcon.temp_ban_player(
    #         steam_id_64="76561198004895814",
    #         player_name=None,
    #         duration=None,
    #         reason=None,
    #         by_admin_name=None,
    #     )
    # )
    # logger.debug(await rcon.remove_temp_ban(TempBanType(steam_id_64="76561198004895814", player_name=None, duration=None, reason=None, admin=None)))
    # bans = await rcon.get_permanent_bans()
    # for line in bans:
    #     print(line)

    # logger.debug(
    #     await rcon.remove_perma_ban(
    #         PermanentBanType(
    #             steam_id_64="76561198004895814",
    #             player_name=None,
    #             timestamp=datetime(
    #                 year=2023, month=3, day=6, hour=20, minute=59, second=29
    #             ),
    #             reason=None,
    #             admin=None,
    #         )
    #     )
    # )
    # logger.debug(await rcon.perma_ban_player("76561198004895814"))

    # bans = await rcon.get_permanent_bans()
    # for line in bans:
    #     print(line)
    # logger.debug(
    #     await rcon.remove_temp_ban(
    #         "76561198004895814 : banned for 2 hours on 2023.03.06-15.23.26"
    #     )
    # )

    # logger.debug(await rcon.get_idle_kick_time())
    # logger.debug(await rcon.set_idle_kick_time(1))
    # logger.debug(await rcon.get_idle_kick_time())
    # logger.debug(await rcon.set_idle_kick_time(0))
    # logger.debug(await rcon.get_idle_kick_time())

    # logs = await rcon.get_game_logs(360)
    # # logger.debug(await rcon.get_game_logs(5))
    # print(f"{len(logs)=}")
    # none_Logs = [l for l in logs if not l]
    # print(f"{len(none_Logs)=}")

    # logger.debug(await rcon.message_player("test message", "76561198004895814"))
    # logger.debug(
    #     await rcon.set_welcome_message(
    #         "Test welcome message\nnext line\n\ntwo lines down"
    #     )
    # )

    # for log in logs:
    #     print(type(log))

    # await rcon.get_num_vip_slots()

    # await rcon.set_num_vip_slots()
    # await rcon.get_num_vip_slots()

    # await rcon.get_max_queue_size()

    # await rcon.connect()


if __name__ == "__main__":
    # trio.run(main, instruments=[Tracer()])
    trio.run(main)
