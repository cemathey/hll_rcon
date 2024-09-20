import inspect
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Generator, Iterable, MutableSequence
from warnings import warn

import pydantic
import trio
from dateutil import parser
from loguru import logger

from hll_rcon import constants
from hll_rcon.connection import HllConnection
from hll_rcon.log_types import (
    BanLog,
    BanLogBan,
    ChatLog,
    ConnectLog,
    DisconnectLog,
    EnteredAdminCamLog,
    ExitedAdminCamLog,
    GameLogType,
    GameServerCredentials,
    KickLog,
    KillLog,
    LogTimeStamp,
    MatchEndLog,
    MatchStartLog,
    MessagedPlayerLog,
    TeamKillLog,
    TeamSwitchLog,
    VoteKickCompletedStatusLog,
    VoteKickExpiredLog,
    VoteKickPlayerVoteLog,
    VoteKickResultsLog,
    VoteKickStartedLog,
)
from hll_rcon.response_types import (
    AdminGroup,
    AdminId,
    AutoBalanceState,
    AutoBalanceThreshold,
    AvailableMaps,
    CensoredWord,
    GameState,
    HighPingLimit,
    IdleKickTime,
    InvalidTempBan,
    MapRotation,
    MaxQueueSize,
    NumVipSlots,
    PermanentBan,
    Player,
    PlayerInfo,
    PlayerScore,
    ServerName,
    ServerPlayerSlots,
    Squad,
    TeamSwitchCoolDown,
    TemporaryBan,
    VipId,
    VoteKickState,
    VoteKickThreshold,
)
from hll_rcon.validators import IntegerGreaterOrEqualToOne


class AsyncRcon:
    """Represents a high level RCON pool of game server connections and returns processed results"""

    # Ban log patterns
    _temp_ban_log_pattern = re.compile(
        r"(.*) :(?: nickname \"(.*)\")? banned for (\d+) hours on ([\d]{4}.[\d]{2}.[\d]{2}-[\d]{2}.[\d]{2}.[\d]{2})(?: for \"(.*)\" by admin \"(.*)\")?",
        re.DOTALL,
    )
    _temp_ban_log_missing_player_id_name_pattern = re.compile(
        r"(.*)? :(?: nickname \"(.*)\")? banned for (\d+) hours on (.*) for \"(.*)\" by admin \"(.*)\"",
        re.DOTALL,
    )
    _perma_ban_log_pattern = re.compile(
        r"(.*) :(?: nickname \"(.*)\")? banned on ([\d]{4}.[\d]{2}.[\d]{2}-[\d]{2}.[\d]{2}.[\d]{2})(?: for \"(.*)\" by admin \"(.*)\")?"
    )

    # Game log patterns
    _kill_teamkill_pattern = re.compile(
        r"(?:(KILL):|(TEAM KILL):) (.*)\((Allies|Axis)\/(.*)\) -> (.*)\((Allies|Axis)\/(.*)\) with (.*)"
    )
    _chat_pattern = re.compile(
        r"CHAT\[(Team|Unit)\]\[(.*)\((Allies|Axis)\/(.*)\)\]: (.*)"
    )
    _connect_disconnect_pattern = re.compile(
        r"(?:(CONNECTED)|(DISCONNECTED)) (.+) \((.*)\)"
    )
    _teamswitch_pattern = re.compile(r"(TEAMSWITCH) (.*) \((.*) > (.*)\)")
    _kick_ban_pattern = re.compile(
        r"(?:(KICK)|(BAN)): \[(.*)\] has been (?:kicked|banned)\. \[(.*)\n?(.*)\]",
        re.DOTALL,
    )
    _vote_kick_pattern = None
    _vote_started_pattern = re.compile(
        r"VOTESYS: Player \[(.*)\] Started a vote of type \((.*)\) against \[(.*)\]. VoteID: \[(\d+)\]"
    )
    _player_voted_pattern = re.compile(
        r"VOTESYS: Player \[(.*)\] voted \[(.*)\] for VoteID\[(\d+)\]"
    )
    _vote_completed_pattern = re.compile(
        r"VOTESYS: Vote \[(\d+)\] completed\. Result: (.*)"
    )
    _vote_expired_pattern = re.compile(
        r"VOTESYS: Vote \[(\d+)\] expired before completion."
    )
    _vote_results_pattern = re.compile(
        r"VOTESYS: Vote Kick {(.*)} successfully passed. \[For: (\d+)\/(\d+) - Against: (\d+)"
    )
    _admin_cam_pattern = r"Player \[(.*) \((.*)\)\] (Entered|Left) Admin Camera"
    _match_start_pattern = re.compile(r"MATCH START (.*) (WARFARE|OFFENSIVE)")
    _match_end_pattern = re.compile(
        r"MATCH ENDED `(.*) (WARFARE|OFFENSIVE)` ALLIED \((\d) - (\d)"
    )
    _message_player_pattern = re.compile(
        r"MESSAGE: player \[(.+)\((.*)\)\], content \[(.+)\]", re.DOTALL
    )

    # Used to split the new line delimited results from get_game_logs() while
    # preserving new lines that are part of the log line
    _log_split_pattern = re.compile(
        r"^\[([\d:.]+ (?:hours|min|sec|ms)) \((\d+)\)\]", re.MULTILINE
    )

    # Miscellaneous parsing patterns
    _gamestate_pattern = re.compile(
        r"Players: Allied: (\d+) - Axis: (\d+)\nScore: Allied: (\d) - Axis: (\d)\nRemaining Time: (\d+):(\d+):(\d+)\nMap: (.*)\nNext Map: (.*)"
    )

    def __init__(
        self,
        ip_addr: str,
        port: str,
        password: str,
        connection_pool_size: int = 1,
        receive_timeout: int = constants.TCP_TIMEOUT_READ,
        tcp_timeout: int = constants.TCP_TIMEOUT,
    ) -> None:
        self._credentials = GameServerCredentials(
            host_ip=pydantic.IPvAnyAddress(ip_addr),  # type: ignore
            host_port=int(port),
            password=password,
        )

        self._receive_timeout = receive_timeout
        self._tcp_timeout = tcp_timeout
        self.connections: list[HllConnection] = []

        try:
            parsed_connection_pool_size = IntegerGreaterOrEqualToOne(
                value=connection_pool_size
            )
        except ValueError:
            raise ValueError(f"connection_pool_size must be a positive integer")

        self.connection_pool_size = parsed_connection_pool_size.value
        self.connection_limit = trio.CapacityLimiter(connection_pool_size)

    async def setup(self) -> None:
        """Create and connect `connection_pool_size` HllConnection instances"""

        async def _inner_setup() -> None:
            connection = await HllConnection.setup(
                self._credentials.host_ip,
                self._credentials.host_port,
                self._credentials.password,
                self._receive_timeout,
                self._tcp_timeout,
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
        """Dole out connections as they are available using a trio.CapacityLimiter

        Will block until a connection is available if there are no free connections
        """
        async with self.connection_limit:
            # in theory we never need to check for a connection being unavailable
            # because trio.CapacityLimiter should handle this for us and block if
            # it needs to wait for another connection
            connection = self.connections.pop()
            yield connection
            self.connections.append(connection)

    @staticmethod
    def _to_hll_list(items: Iterable[str], separator: str = ",") -> str:
        """Convert to a comma separated list for the game server"""
        return separator.join(items)

    @staticmethod
    def _from_hll_list(raw_list: str, separator="\t") -> list[str]:
        """Convert a game server tab delimited result string to a native list

        Raises
            ValueError: if the parsed number of items is less than the indicated number of items,
                does not raise if extra items are present because some commands such as get_temp_bans
                return results with empty entries and others include trailing values so it is difficult
                to definitively establish how many elements are in a list
        """
        expected_length, *items = raw_list.split(separator)
        expected_length = int(expected_length)

        if len(items) == 1 and not items[0]:
            return []

        if len(items) < expected_length:
            logger.debug(f"{expected_length=}")
            logger.debug(f"{len(items)=}")
            logger.debug(f"{items=}")

        if len(items) > 0 and items[0] and not items[-1]:
            logger.debug(f"{items[:-1]=}")
            return items[:-1]
            # raise ValueError("List does not match expected length")

        return items

    async def get_server_name(
        self, output: MutableSequence | None = None
    ) -> ServerName:
        """Return the server name as defined in the game server `Server.ini` file"""
        async with self._get_connection() as conn:
            result = await conn.get_server_name()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        validated_result = ServerName(name=result)

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_get_current_max_player_slots(slots: str) -> ServerPlayerSlots:
        current_players, max_players = slots.split("/")
        return ServerPlayerSlots(
            current_players=int(current_players), max_players=int(max_players)
        )

    async def get_current_max_player_slots(
        self, output: MutableSequence | None = None
    ) -> ServerPlayerSlots:
        """Return the number of players currently on the server and max players"""
        async with self._get_connection() as conn:
            result = await conn.get_current_max_player_slots()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        validated_result = self._parse_get_current_max_player_slots(result)

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_gamestate(raw_gamestate: str) -> GameState:
        if match := re.match(AsyncRcon._gamestate_pattern, raw_gamestate):
            (
                allied_players,
                axis_players,
                allied_score,
                axis_score,
                hours,
                mins,
                secs,
                current_map,
                next_map,
            ) = match.groups()
            return GameState(
                allied_players=int(allied_players),
                axis_players=int(axis_players),
                allied_score=int(allied_score),
                axis_score=int(axis_score),
                remaining_time=timedelta(
                    hours=float(hours), minutes=float(mins), seconds=float(secs)
                ),
                current_map=current_map,
                next_map=next_map,
            )
        else:
            raise ValueError(
                f"Game server returned invalid results for get_gamestate()"
            )

    async def get_gamestate(self, output: MutableSequence | None = None) -> GameState:
        """Return the current round state"""
        async with self._get_connection() as conn:
            result = await conn.get_gamestate()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        validated_result = self._parse_gamestate(result)

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_max_queue_size(
        self, output: MutableSequence | None = None
    ) -> MaxQueueSize:
        """Return the maximum number of players allowed in the queue to join the server"""
        async with self._get_connection() as conn:
            result = await conn.get_max_queue_size()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        validated_result = MaxQueueSize(size=int(result))

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_max_queue_size(
        self, size: int, output: MutableSequence | None = None
    ) -> bool:
        """Set the maximum number of players allowed in the queue to join the server (0 <= size <= 6)"""
        if not 0 <= size <= 6:
            warn(
                "The game server does not support queue sizes outside of 0 <= size <= 6"
            )
        async with self._get_connection() as conn:
            result = await conn.set_max_queue_size(size=size)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_num_vip_slots(
        self, output: MutableSequence | None = None
    ) -> NumVipSlots:
        """Returns the number of reserved VIP slots"""
        async with self._get_connection() as conn:
            result = await conn.get_num_vip_slots()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        validated_result = NumVipSlots(count=int(result))

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_num_vip_slots(
        self, amount: int, output: MutableSequence | None = None
    ) -> bool:
        """Set the number of reserved VIP slots on the server

        For example, setting this to 2 on a 100 slot server would only allow players
        with VIP access to join once 98 players are connected (regardless of those
        players VIP status)
        """
        try:
            args = IntegerGreaterOrEqualToOne(value=amount)
        except ValueError as e:
            logger.error(f"{amount=} must be a positive integer")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_num_vip_slots(args.value)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_welcome_message(
        self, message: str, output: MutableSequence | None = None
    ) -> bool:
        """Set the server welcome message"""
        async with self._get_connection() as conn:
            result = await conn.set_welcome_message(message=message)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_broadcast_message(
        self, message: str | None, output: MutableSequence | None = None
    ) -> bool:
        """Set the current broadcast message, or clear it if message is None

        As of HLL v1.13.0.815373 resetting the broadcast message outside of the in game console is broken
        """
        async with self._get_connection() as conn:
            result = await conn.set_broadcast_message(message=message)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def clear_broadcast_message(
        self, output: MutableSequence | None = None
    ) -> bool:
        """Clear the current broadcast message

        As of HLL v1.13.0.815373 resetting the broadcast message outside of the in game console is broken
        """
        async with self._get_connection() as conn:
            result = await conn.clear_broadcast_message()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _relative_time_to_timedelta(relative_time: str) -> timedelta:
        """Convert a relative HLL game log timestamp to a timedelta"""
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
    def _absolute_time_to_datetime(absolute_time: str) -> datetime:
        """Convert a Unix UTC timestamp to a native datetime"""
        # Game server time stamps are already UTC
        return datetime.fromtimestamp(float(absolute_time), tz=timezone.utc)

    @staticmethod
    def _parse_game_log(
        raw_log: str, relative_time: str, absolute_time: str
    ) -> (
        BanLog
        | ChatLog
        | ConnectLog
        | DisconnectLog
        | EnteredAdminCamLog
        | ExitedAdminCamLog
        | KickLog
        | KillLog
        | MatchEndLog
        | MatchStartLog
        | MessagedPlayerLog
        | TeamKillLog
        | TeamSwitchLog
        | VoteKickExpiredLog
        | VoteKickCompletedStatusLog
        | VoteKickPlayerVoteLog
        | VoteKickResultsLog
        | VoteKickStartedLog
        | None
    ):
        """Parse a raw HLL game log instance to an aware pydantic.BaseModel type"""
        time = LogTimeStamp(
            absolute_timestamp=AsyncRcon._absolute_time_to_datetime(absolute_time),
            relative_timestamp=AsyncRcon._relative_time_to_timedelta(relative_time),
        )

        def _hash_log(log: str) -> bytes:
            import hashlib

            return hashlib.sha1(string=log.encode()).digest()

        if raw_log.startswith("KILL") or raw_log.startswith("TEAM KILL"):
            if match := re.match(AsyncRcon._kill_teamkill_pattern, raw_log):
                (
                    kill,
                    team_kill,
                    player_name,
                    player_team,
                    player_id,
                    victim_player_name,
                    victim_team,
                    victim_player_id,
                    weapon,
                ) = match.groups()

                if kill:
                    return KillLog(
                        player_id=player_id,
                        player_name=player_name,
                        player_team=player_team,
                        victim_player_id=victim_player_id,
                        victim_player_name=victim_player_name,
                        victim_team=victim_team,
                        weapon=weapon,
                        time=time,
                        id=_hash_log(log=raw_log),
                    )
                else:
                    return TeamKillLog(
                        player_id=player_id,
                        player_name=player_name,
                        player_team=player_team,
                        victim_player_id=victim_player_id,
                        victim_player_name=victim_player_name,
                        victim_team=victim_team,
                        weapon=weapon,
                        time=time,
                        id=_hash_log(log=raw_log),
                    )

        elif raw_log.startswith("CHAT"):
            if match := re.match(AsyncRcon._chat_pattern, raw_log):
                scope, player_name, team, player_id, content = match.groups()
                return ChatLog(
                    player_id=player_id,
                    player_name=player_name,
                    player_team=team,
                    scope=scope,
                    content=content,
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            else:
                ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("CONNECTED") or raw_log.startswith("DISCONNECTED"):
            if match := re.match(AsyncRcon._connect_disconnect_pattern, raw_log):
                connected, disconnected, player_name, player_id = match.groups()
                if connected:
                    return ConnectLog(
                        player_id=player_id,
                        player_name=player_name,
                        time=time,
                        id=_hash_log(log=raw_log),
                    )
                else:
                    return DisconnectLog(
                        player_id=player_id,
                        player_name=player_name,
                        time=time,
                        id=_hash_log(log=raw_log),
                    )
            else:
                ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("TEAMSWITCH"):
            if match := re.match(AsyncRcon._teamswitch_pattern, raw_log):
                action, player_name, from_team, to_team = match.groups()
                return TeamSwitchLog(
                    player_name=player_name,
                    from_team=from_team,
                    to_team=to_team,
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            else:
                ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("BAN") or raw_log.startswith("KICK"):
            if match := re.match(AsyncRcon._kick_ban_pattern, raw_log):
                (
                    kick,
                    ban,
                    player_name,
                    raw_removal_type,
                    # duration,
                    removal_reason,
                ) = match.groups()

                # removal_reason = None
                ban_duration = None

                if kick:
                    if raw_removal_type.startswith("YOU WERE"):
                        removal_type = constants.IDLE_KICK
                        removal_reason = raw_removal_type.strip()
                    elif raw_removal_type.startswith("Host"):
                        # logger.warning(f"{removal_reason=} {raw_log=}")
                        removal_type = constants.HOST_CLOSED_CONNECTION_KICK
                        removal_reason = raw_removal_type.strip()
                    elif raw_removal_type.startswith("KICKED FOR"):
                        removal_type = constants.TEAM_KILLING_KICK
                        removal_reason = raw_removal_type.strip()
                    elif raw_removal_type.startswith("KICKED BY THE"):
                        removal_type = constants.ADMIN_KICK
                        _, removal_reason = raw_removal_type.split("!", maxsplit=1)
                        removal_reason = removal_reason.strip()
                    elif raw_removal_type.startswith("Anti-"):
                        removal_type = constants.ANTI_CHEAT_TIMEOUT_KICK
                        removal_reason = raw_removal_type.strip()
                    elif raw_removal_type.startswith("BANNED FOR"):
                        removal_type = constants.TEMPORARY_BAN_KICK
                        _, removal_reason = raw_removal_type.split("!", maxsplit=1)
                        removal_reason = removal_reason.strip()
                    elif raw_removal_type.startswith("PERMANENTLY"):
                        removal_type = constants.PERMANENT_BAN_KICK
                        _, removal_reason = raw_removal_type.split("!", maxsplit=1)
                        removal_reason = removal_reason.strip()
                    else:
                        removal_type = "invalid"
                        logger.error(f"invalid {raw_removal_type=} {raw_log=}")
                        # raise ValueError(f"invalid {raw_removal_type=} {raw_log=}")

                    if removal_reason == "":
                        logger.error(f"invalid {removal_reason=}")

                    return KickLog(
                        player_name=player_name,
                        kick_type=removal_type,
                        reason=removal_reason,
                        time=time,
                        id=_hash_log(log=raw_log),
                    )
                else:
                    if raw_removal_type.startswith(
                        "PERMA"
                    ) or raw_removal_type.startswith("BAN"):
                        _, removal_reason = raw_removal_type.split("!", maxsplit=1)
                        removal_reason = removal_reason.strip()
                    else:
                        logger.warning(f"no match for {raw_removal_type=}")

                    # logger.warning(f"{ban=} {removal_reason=}")
                    if duration_match := re.match(
                        r"BANNED FOR (\d+) HOURS", raw_removal_type
                    ):
                        ban_duration = int(duration_match.groups()[0])
                        ban_type = BanLogBan.TEMPORARY_BAN
                    else:
                        ban_type = BanLogBan.PERMANENT_BAN

                    if removal_reason is None or removal_reason == "":
                        # logger.error(
                        #     f"{player_name=} {ban_type=} {ban_duration=} {removal_reason=}"
                        # )
                        logger.error(f"{raw_log=}")

                    return BanLog(
                        player_name=player_name,
                        ban_type=ban_type,
                        ban_duration_hours=ban_duration,
                        reason=removal_reason,
                        time=time,
                        id=_hash_log(log=raw_log),
                    )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("MATCH"):
            if match := re.match(AsyncRcon._match_start_pattern, raw_log):
                map_name, game_mode = match.groups()
                return MatchStartLog(
                    map_name=map_name,
                    game_mode=game_mode,
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            elif match := re.match(AsyncRcon._match_end_pattern, raw_log):
                map_name, game_mode, allied_score, axis_score = match.groups()
                return MatchEndLog(
                    map_name=map_name,
                    game_mode=game_mode,
                    allied_score=int(allied_score),
                    axis_score=int(axis_score),
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("Player"):
            if match := re.match(AsyncRcon._admin_cam_pattern, raw_log):
                player_name, player_id, entered_exited = match.groups()

                if entered_exited == "Entered":
                    return EnteredAdminCamLog(
                        player_id=player_id,
                        player_name=player_name,
                        time=time,
                        id=_hash_log(log=raw_log),
                    )
                elif entered_exited == "Left":
                    return ExitedAdminCamLog(
                        player_id=player_id,
                        player_name=player_name,
                        time=time,
                        id=_hash_log(log=raw_log),
                    )
                else:
                    raise ValueError(f"invalid {entered_exited=} {raw_log=}")
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("VOTESYS"):
            if match := re.match(AsyncRcon._player_voted_pattern, raw_log):
                player_name, vote_type, vote_id = match.groups()
                return VoteKickPlayerVoteLog(
                    player_name=player_name,
                    vote_type=vote_type,
                    vote_id=int(vote_id),
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            elif match := re.match(AsyncRcon._vote_completed_pattern, raw_log):
                vote_id, vote_result = match.groups()
                return VoteKickCompletedStatusLog(
                    vote_result=vote_result,
                    vote_id=int(vote_id),
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            elif match := re.match(AsyncRcon._vote_expired_pattern, raw_log):
                vote_id = match.groups()[0]
                return VoteKickExpiredLog(
                    vote_id=int(vote_id), time=time, id=_hash_log(log=raw_log)
                )
            elif match := re.match(AsyncRcon._vote_started_pattern, raw_log):
                player_name, vote_type, victim_player_name, vote_id = match.groups()
                return VoteKickStartedLog(
                    player_name=player_name,
                    victim_player_name=victim_player_name,
                    vote_type=vote_type,
                    vote_id=int(vote_id),
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            elif match := re.match(AsyncRcon._vote_results_pattern, raw_log):
                (
                    victim_player_name,
                    for_votes,
                    votes_required,
                    against_votes,
                ) = match.groups()
                return VoteKickResultsLog(
                    victim_player_name=victim_player_name,
                    for_votes=int(for_votes),
                    against_votes=int(against_votes),
                    votes_required=int(votes_required),
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("MESSAGE"):
            if match := re.match(AsyncRcon._message_player_pattern, raw_log):
                player_name, player_id, message = match.groups()
                return MessagedPlayerLog(
                    player_id=player_id,
                    player_name=player_name,
                    message=message,
                    time=time,
                    id=_hash_log(log=raw_log),
                )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        else:
            logger.error(f"Unable to parse `{raw_log}` (fell through)")
            # raise ValueError(f"Unable to parse `{raw_log}` (fell through)")

    @staticmethod
    def split_raw_log_lines(
        raw_logs: str,
    ) -> Generator[tuple[str, str, str], None, None]:
        """Split raw game server logs into the line, relative time and absolute UTC timestamp

        Yields
            A tuple of the actual log content, the relative time and timestamp as strings
        """
        if raw_logs != "":
            logs = raw_logs.strip("\n")
            split_logs = re.split(AsyncRcon._log_split_pattern, logs)

            # The first entry is an empty string because of re.split matching group behavior
            # but if the overall number of splits isn't divisible by 3 (number of splits)
            # then we have an issue and have a malformed result, or broken split pattern
            if (len(split_logs) - 1) % 3 != 0:
                raise ValueError(
                    f"Received an incomplete game log result from the game server"
                )

            for raw_relative_time, raw_timestamp, raw_log_line in zip(
                split_logs[1::3], split_logs[2::3], split_logs[3::3]
            ):
                yield raw_log_line.strip(), raw_relative_time, raw_timestamp,

    async def get_game_logs(
        self,
        minutes: int,
        filter: str | None = None,
        output: MutableSequence | None = None,
    ) -> GameLogType:
        """Split and parse raw game logs into aware pydantic.BaseModel types"""
        async with self._get_connection() as conn:
            result = await conn.get_game_logs(minutes=minutes, filter=filter)
            # Incredibly spammy if enabled
            # logger.debug(
            #     f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            # )

        if result == constants.EMPTY_RESPONSE:
            return []
        else:
            logs = []
            for raw_log, relative_time, absolute_time in AsyncRcon.split_raw_log_lines(
                result
            ):
                logs.append(
                    AsyncRcon._parse_game_log(raw_log, relative_time, absolute_time)
                )

        if output is not None:
            output.append(logs)

        return logs

    async def get_current_map(self, output: MutableSequence | None = None) -> str:
        """Return the current map name"""
        async with self._get_connection() as conn:
            result = await conn.get_current_map()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )
        if output is not None:
            output.append(result)

        return result

    async def get_available_maps(
        self, output: MutableSequence | None = None
    ) -> AvailableMaps:
        """Return a list of all available map names (not the current map rotation)."""
        async with self._get_connection() as conn:
            result = await conn.get_available_maps()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        map_names = self._from_hll_list(result)
        validated_result = AvailableMaps(maps=[name for name in map_names])

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_map_rotation(
        self, output: MutableSequence | None = None
    ) -> MapRotation:
        """Return a list of the currently set map rotation names"""
        async with self._get_connection() as conn:
            result = await conn.get_map_rotation()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        map_names = self._from_hll_list(result)
        validated_result = MapRotation(maps=[name for name in map_names])

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def add_map_to_rotation(
        self,
        name: str,
        after_map_name: str | None = None,
        after_map_ordinal: int | None = None,
        output: MutableSequence | None = None,
    ) -> bool:
        """Add the map to the rotation in the specified spot, appends to the end of the rotation by default"""
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
        if result not in (
            constants.SUCCESS_RESPONSE,
            constants.FAIL_MAP_REMOVAL_RESPONSE,
        ):
            logger.error(
                f"add_map_to_rotation({name=} {after_map_name=} {after_map_ordinal=})=result"
            )
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def remove_map_from_rotation(
        self,
        name: str,
        ordinal: int | None = 1,
        output: MutableSequence | None = None,
    ) -> bool:
        """Remove the specified map instance from the rotation"""
        async with self._get_connection() as conn:
            result = await conn.remove_map_from_rotation(name=name, ordinal=ordinal)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (
            constants.SUCCESS_RESPONSE,
            constants.FAIL_MAP_REMOVAL_RESPONSE,
        ):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_current_map(
        self,
        name: str,
        ordinal: int | None = 1,
        output: MutableSequence | None = None,
    ) -> bool:
        """Immediately change the game server to the map after a 60 second delay, the map must be in the rotation"""
        async with self._get_connection() as conn:
            result = await conn.set_current_map(name=name, ordinal=ordinal)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_players(
        self,
        output: MutableSequence | None = None,
    ) -> list[str]:
        """Return a list of player names currently connected to the game server"""
        async with self._get_connection() as conn:
            result = await conn.get_players()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        validated_result = [name for name in AsyncRcon._from_hll_list(result)]

        # HLL likes to return the delimeter at the end of the last entry
        # even though there isn't another result
        if validated_result[-1] == "":
            validated_result = validated_result[:-1]
        else:
            validated_result = validated_result

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_get_player_ids(
        name_and_ids: list[str],
    ) -> dict[str, Player]:
        """Parse name and steam ID pairs into dictionaries"""
        # player_id_64_lookup: dict[str, str] = {}
        # player_name_lookup: dict[str, str] = {}

        player_id_lookup: dict[str, Player] = {}
        for pair in name_and_ids:
            player_name, player_id = pair.split(" : ")
            # player_id_64_lookup[player_id] = player_name
            # player_name_lookup[player_name] = player_id
            player = Player(player_name=player_name, player_id=player_id)
            player_id_lookup[player_id] = player

        # return player_id_64_lookup, player_name_lookup
        return player_id_lookup

    async def get_player_ids(
        self, output: MutableSequence | None = None
    ) -> dict[str, Player]:
        """Get the player names and player IDs of all the players currently connected to the game server

        Returns
            A tuple of dictionaries, player_id: player_name and player_name: player_id
        """
        async with self._get_connection() as conn:
            result = await conn.get_player_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        entries = self._from_hll_list(result)
        validated_result = self._parse_get_player_ids(entries)

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_get_admin_id(raw_admin_id: str) -> AdminId:
        player_id, role, quoted_name = raw_admin_id.split(" ", maxsplit=2)
        return AdminId(
            player_id=player_id,
            role=AdminGroup(role=role),
            name=quoted_name[1:-1],
        )

    async def get_admin_ids(
        self,
        output: MutableSequence | None = None,
    ) -> list[AdminId]:
        """Return each player ID that has an admin role on the server, see also get_admin_groups()"""
        async with self._get_connection() as conn:
            result = await conn.get_admin_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        admin_ids = self._from_hll_list(result)
        validated_result = [
            self._parse_get_admin_id(admin_id) for admin_id in admin_ids
        ]

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_admin_groups(
        self,
        output: MutableSequence | None = None,
    ) -> list[AdminGroup]:
        """Return a list of available admin roles"""
        async with self._get_connection() as conn:
            result = await conn.get_admin_groups()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        group_names = AsyncRcon._from_hll_list(result)
        validated_result = [AdminGroup(role=name) for name in group_names]

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def add_admin(
        self,
        player_id: str,
        role: str,
        name: str | None = None,
        output: MutableSequence | None = None,
    ) -> bool:
        """Grant admin role access to a player ID

        Args
            player_id: The users player ID
            role: A valid HLL admin role, see get_admin_groups()
            name: An optional display name, the game server will accept anything here
                there is no necessary correlation to the names the player ID plays with on the game server
        """
        async with self._get_connection() as conn:
            result = await conn.add_admin(player_id=player_id, role=role, name=name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def remove_admin(
        self,
        player_id: str,
        output: MutableSequence | None = None,
    ) -> bool:
        """Remove all admin roles from the specified steam ID, see get_admin_groups() for possible admin roles"""
        async with self._get_connection() as conn:
            result = await conn.remove_admin(player_id=player_id)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_get_vip_id(vip_id: str) -> VipId:
        player_id, quoted_name = vip_id.split(" ", maxsplit=1)
        return VipId(player_id=player_id, name=quoted_name[1:-1])

    async def get_vip_ids(
        self,
        output: MutableSequence | None = None,
    ) -> list[VipId]:
        """Return a HLL tab delimited list of VIP player IDs and names"""
        async with self._get_connection() as conn:
            result = await conn.get_vip_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        vip_ids = AsyncRcon._from_hll_list(result)
        validated_result = [self._parse_get_vip_id(vip_id) for vip_id in vip_ids]

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_player_info(raw_player_info: str) -> PlayerInfo | None:
        if raw_player_info == constants.FAIL_RESPONSE:
            return None

        lines = raw_player_info.strip().split("\n")
        if len(lines) == 1:
            raise ValueError(
                f"Received an invalid or incomplete `PlayerInfo`=`{raw_player_info}` from the game server"
            )

        player_name: str | None = None
        player_id: str | None = None
        raw_team: str | None = None
        team: str | None = None
        role: str | None = None
        unit: Squad | None = None
        loadout: str | None = None
        kills: str | None = None
        deaths: str | None = None
        level: str | None = None

        raw_scores = ""
        scores: dict[str, int] = {}

        for line in lines:
            if line.startswith("Name"):
                _, player_name = line.split("Name: ")
            elif line.startswith("steam"):
                _, player_id = line.split("steamID64: ")
            elif line.startswith("Team"):
                _, raw_team = line.split("Team: ")
            elif line.startswith("Role"):
                _, role = line.split("Role: ")
            elif line.startswith("Unit"):
                left, unit_name = line.split(" - ")
                _, unit_id = left.split("Unit: ")
                unit = Squad(unit_id=int(unit_id), unit_name=unit_name)
            elif line.startswith("Loadout"):
                _, loadout = line.split("Loadout: ")
            elif line.startswith("Kills"):
                left, right = line.split(" - ")
                _, kills = left.split("Kills: ")
                _, deaths = right.split("Deaths: ")
            elif line.startswith("Score"):
                _, raw_scores = line.split("Score: ")
            elif line.startswith("Level"):
                _, level = line.split("Level: ")

        if raw_team == "None":
            team = None
        else:
            team = raw_team

        for raw_score in raw_scores.split(","):
            key, score = raw_score.split(maxsplit=1)
            scores[key] = int(score)

        if any(
            key is None for key in (player_name, player_id, kills, deaths, role, level)
        ):
            logger.error(f"{raw_player_info}")
            raise ValueError(
                f"Received an invalid or incomplete `PlayerInfo`=`{raw_player_info}` from the game server"
            )

        processed_score = PlayerScore(
            kills=int(kills),  # type: ignore
            deaths=int(deaths),  # type: ignore
            combat=scores["C"],
            offensive=scores["O"],
            defensive=scores["D"],
            support=scores["S"],
        )

        return PlayerInfo(
            player_name=player_name,  # type: ignore
            player_id=player_id,  # type: ignore
            team=team,
            unit=unit,
            loadout=loadout,
            role=role,  # type: ignore
            score=processed_score,
            level=int(level),  # type: ignore
        )

    async def get_player_info(
        self, player_name: str, output: MutableSequence | None = None
    ) -> PlayerInfo | None:
        """Return detailed player info for the given player name"""
        if not player_name:
            raise ValueError("Must provide a player name")

        async with self._get_connection() as conn:
            result = await conn.get_player_info(player_name=player_name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=} {player_name=}"  # type: ignore
            )

        # logger.warning(f"{result=} {player_name=}")
        validated_result = self._parse_player_info(result)

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def add_vip(
        self, player_id: str, name: str | None, output: MutableSequence | None = None
    ) -> bool:
        """Grant VIP status to the given player ID

        Args
            player_id: The users player ID
            name: An optional display name, the game server will accept anything here
                there is no necessary correlation to the names the player ID plays with on the game server
        """
        async with self._get_connection() as conn:
            result = await conn.add_vip(player_id=player_id, name=name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def remove_vip(
        self, player_id: str, output: MutableSequence | None = None
    ) -> bool:
        """Remove VIP status from the given player ID"""
        async with self._get_connection() as conn:
            result = await conn.remove_vip(player_id=player_id)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_ban_log_timestamp(raw_timestamp: str) -> datetime:
        _date, _time = raw_timestamp.split("-")
        _time = _time.replace(".", ":")

        timestamp = parser.parse(f"{_date} {_time}")
        return timestamp.replace(tzinfo=timezone.utc)

    @staticmethod
    def _parse_temp_ban_log(raw_ban: str) -> TemporaryBan | InvalidTempBan:
        """Parse a raw HLL ban log into a TempBanType or InvalidTempBanType

        As of HLL v1.13.0.815373 under some (unknown) circumstances the game server will
        return a temp ban log that includes neither the player ID or player name:
            ex: : banned for 46368 hours on 2023.02.20-17.47.55 for "Homophobic statements are not tolerated." by admin "-Scab"

        Temporary ban logs are in the format:
            76561199023367826 : nickname "(WTH) Abu" banned for 2 hours on 2021.12.09-16.40.08 for "Being a troll" by admin "Some Admin Name"
        """
        # TODO: Account for any other optional fields
        # I do not remember what fields are optional?
        if match := re.match(AsyncRcon._temp_ban_log_pattern, raw_ban):
            (
                player_id,
                player_name,
                duration_hours,
                raw_timestamp,
                reason,
                admin,
            ) = match.groups()

            timestamp = AsyncRcon._parse_ban_log_timestamp(raw_timestamp)

            ban = TemporaryBan(
                player_id=player_id,
                player_name=player_name,
                duration_hours=int(duration_hours),
                timestamp=timestamp,
                reason=reason,
                admin=admin,
            )
        elif match := re.match(
            AsyncRcon._temp_ban_log_missing_player_id_name_pattern, raw_ban
        ):
            (
                player_id,
                player_name,
                duration_hours,
                raw_timestamp,
                reason,
                admin,
            ) = match.groups()

            timestamp = AsyncRcon._parse_ban_log_timestamp(raw_timestamp)

            ban = InvalidTempBan(
                player_id=player_id,
                player_name=player_name,
                duration_hours=int(duration_hours),
                timestamp=timestamp,
                reason=reason,
                admin=admin,
            )
        else:
            raise ValueError(f"Received invalid temp ban log: `{raw_ban}`")

        return ban

    async def get_temp_bans(
        self, output: MutableSequence | None = None
    ) -> list[TemporaryBan | InvalidTempBan]:
        """Return all the temporary bans on the game server"""
        async with self._get_connection() as conn:
            result = await conn.get_temp_bans()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        raw_results = AsyncRcon._from_hll_list(result)

        validated_result = [
            AsyncRcon._parse_temp_ban_log(raw_ban) for raw_ban in raw_results if raw_ban
        ]

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_perma_ban_log(raw_ban: str) -> PermanentBan:
        """Parse a raw HLL ban log

        Permanent ban logs are in the format:
            76561197975123456 : nickname "Georgij Zhukov Sovie" banned on 2022.12.06-16.27.14 for "Racism" by admin "BLACKLIST: NoodleArms"
        """
        # TODO: Account for any other optional fields
        # I do not remember what fields are optional?
        if match := re.match(AsyncRcon._perma_ban_log_pattern, raw_ban):
            (
                player_id,
                player_name,
                raw_timestamp,
                reason,
                admin,
            ) = match.groups()

            timestamp = AsyncRcon._parse_ban_log_timestamp(raw_timestamp)

            ban = PermanentBan(
                player_id=player_id,
                player_name=player_name,
                timestamp=timestamp,
                reason=reason,
                admin=admin,
            )
        else:
            raise ValueError(f"Received invalid perma ban log: `{raw_ban}`")

        return ban

    async def get_permanent_bans(
        self, output: MutableSequence | None = None
    ) -> list[PermanentBan]:
        """Return all the permanent bans on the game server"""
        async with self._get_connection() as conn:
            result = await conn.get_permanent_bans()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        raw_results = AsyncRcon._from_hll_list(result)
        validated_result = [
            AsyncRcon._parse_perma_ban_log(raw_ban)
            for raw_ban in raw_results
            if raw_ban
        ]

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def message_player(
        self,
        message: str,
        player_id: str | None = None,
        player_name: str | None = None,
        output: MutableSequence | None = None,
    ) -> bool:
        """Send an in game message to the specified player"""
        if player_id is None and player_name is None:
            raise ValueError(constants.PLAYER_ID_64_OR_PLAYER_NAME_REQUIRED_ERROR_MSG)

        async with self._get_connection() as conn:
            result = await conn.message_player(
                message=message, player_id=player_id, player_name=player_name
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def punish_player(
        self,
        player_name: str,
        reason: str | None = None,
        output: MutableSequence | None = None,
    ) -> bool:
        """Punish (kill in game) the specified player, will fail if they are not spawned"""
        async with self._get_connection() as conn:
            result = await conn.punish_player(player_name=player_name, reason=reason)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def switch_player_on_death(
        self,
        player_name: str,
        output: MutableSequence | None = None,
    ) -> bool:
        """Switch a player to the other team after their next death"""
        async with self._get_connection() as conn:
            result = await conn.switch_player_on_death(player_name=player_name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def switch_player_now(
        self,
        player_name: str,
        output: MutableSequence | None = None,
    ) -> bool:
        """Immediately switch a player to the other team"""
        async with self._get_connection() as conn:
            result = await conn.switch_player_now(player_name=player_name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def kick_player(
        self,
        player_name: str,
        reason: str | None = None,
        output: MutableSequence | None = None,
    ) -> bool:
        """Remove a player from the server and show them the indicated reason"""
        async with self._get_connection() as conn:
            result = await conn.kick_player(player_name=player_name, reason=reason)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def temp_ban_player(
        self,
        player_id: str | None = None,
        player_name: str | None = None,
        duration_hours: int | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
        output: MutableSequence | None = None,
    ) -> bool:
        """Ban a player from the server for the given number of hours and show them the indicated reason

        Args
            player_id: optional if player name is provided
            player_name: optional if player_id is provided, will use player_id if both are passed
            duration_hours: number of hours to ban, will be cleared on game server restart, defaults to 2 if not provided
            reason: optional reason for the ban that is shown to the player
            by_admin_name: optional name for which admin or automated service banned the player
        """
        if player_id is None and player_name is None:
            raise ValueError(constants.PLAYER_ID_64_OR_PLAYER_NAME_REQUIRED_ERROR_MSG)

        try:
            args = IntegerGreaterOrEqualToOne(value=duration_hours)
        except ValueError:
            raise ValueError(f"`duration` must be an integer >= 1 or None")

        async with self._get_connection() as conn:
            result = await conn.temp_ban_player(
                player_id=player_id,
                player_name=player_name,
                duration_hours=args.value,
                reason=reason,
                by_admin_name=by_admin_name,
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def perma_ban_player(
        self,
        player_id: str | None = None,
        player_name: str | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
        output: MutableSequence | None = None,
    ) -> bool:
        """Permanently ban a player and show them the indicated reason

        Args
            player_id: optional if player name is provided
            player_name: optional if player_id is provided, will use player_id if both are passed
            reason: optional reason for the ban that is shown to the player
            by_admin_name: optional name for which admin or automated service banned the player

        Returns
            SUCCESS or FAIL
        """
        if player_id is None and player_name is None:
            raise ValueError(constants.PLAYER_ID_64_OR_PLAYER_NAME_REQUIRED_ERROR_MSG)

        async with self._get_connection() as conn:
            result = await conn.perma_ban_player(
                player_id=player_id,
                player_name=player_name,
                reason=reason,
                by_admin_name=by_admin_name,
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def remove_temp_ban(
        self,
        ban_log: str | TemporaryBan,
        output: MutableSequence | None = None,
    ) -> bool:
        """Remove a temporary ban from a player

        Args
            ban_log: Must match the HLL ban log format returned from get_temp_bans
        """

        if isinstance(ban_log, InvalidTempBan):
            logger.warning(
                f"{ban_log=} is an InvalidTempBanType, attempting unban regardless"
            )

        if isinstance(ban_log, str):
            self._parse_temp_ban_log(ban_log)
        else:
            ban_log = str(ban_log)

        async with self._get_connection() as conn:
            result = await conn.remove_temp_ban(ban_log=ban_log)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def remove_perma_ban(
        self,
        ban_log: str | PermanentBan,
        output: MutableSequence | None = None,
    ) -> bool:
        """Remove a permanent ban from a player

        Args
            ban_log: Must match the HLL ban log format returned from get_permanent_bans()
        """

        if isinstance(ban_log, str):
            self._parse_perma_ban_log(ban_log)
        else:
            ban_log = str(ban_log)

        async with self._get_connection() as conn:
            result = await conn.remove_perma_ban(ban_log=ban_log)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_idle_kick_time(
        self,
        output: MutableSequence | None = None,
    ) -> IdleKickTime:
        """Return the current idle kick time in minutes"""
        async with self._get_connection() as conn:
            result = await conn.get_idle_kick_time()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        validated_result = IdleKickTime(kick_time=result)

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_idle_kick_time(
        self,
        threshold_minutes: int,
        output: MutableSequence | None = None,
    ) -> bool:
        """Set the idle kick time in minutes"""
        args = IdleKickTime(kick_time=threshold_minutes)

        async with self._get_connection() as conn:
            result = await conn.set_idle_kick_time(threshold_minutes=args.kick_time)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_high_ping_limit(
        self,
        output: MutableSequence | None = None,
    ) -> HighPingLimit:
        """Return the high ping limit (player is kicked when they exceed) in milliseconds"""
        async with self._get_connection() as conn:
            result = await conn.get_high_ping_limit()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = HighPingLimit(limit=result)
        except ValueError:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_high_ping_limit(
        self,
        threshold: int,
        output: MutableSequence | None = None,
    ) -> bool:
        """Set the high ping limit (player is kicked when they exceed) in milliseconds"""
        args = HighPingLimit(limit=threshold)

        async with self._get_connection() as conn:
            result = await conn.set_high_ping_limit(threshold=args.limit)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def disable_high_ping_limit(
        self,
        output: MutableSequence | None = None,
    ) -> bool:
        """Disable (set to 0) the high ping limit"""
        async with self._get_connection() as conn:
            result = await conn.disable_high_ping_limit()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_team_switch_cooldown(
        self,
        output: MutableSequence | None = None,
    ) -> TeamSwitchCoolDown:
        """Return the current team switch cool down in minutes"""
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

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_team_switch_cooldown(
        self,
        cooldown: int,
        output: MutableSequence | None = None,
    ) -> bool:
        """Set the team switch cool down in minutes"""
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

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_auto_balance_enabled(
        self, output: MutableSequence | None = None
    ) -> AutoBalanceState:
        """Return if team auto balance (enforced differences in team sizes) is enabled"""
        async with self._get_connection() as conn:
            result = await conn.get_auto_balance_enabled()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = AutoBalanceState(state=result)  # type: ignore
        except ValueError:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def enable_auto_balance(self, output: MutableSequence | None = None) -> bool:
        """Enable the team auto balance (enforced differences in team sizes) feature"""
        async with self._get_connection() as conn:
            result = await conn.enable_auto_balance()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def disable_auto_balance(self, output: MutableSequence | None = None) -> bool:
        """Disable the team auto balance (enforced differences in team sizes) feature"""
        async with self._get_connection() as conn:
            result = await conn.disable_auto_balance()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_auto_balance_threshold(
        self, output: MutableSequence | None = None
    ) -> AutoBalanceState:
        """Return the allowed team size difference before players are forced to join the other team"""
        async with self._get_connection() as conn:
            result = await conn.get_auto_balance_threshold()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = AutoBalanceState(threshold=result)  # type: ignore
        except ValueError:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def set_auto_balance_threshold(
        self, threshold: int, output: MutableSequence | None = None
    ) -> bool:
        """Set the allowed team size difference before players are forced to join the other team"""
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

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_vote_kick_enabled(
        self, output: MutableSequence | None = None
    ) -> VoteKickState:
        """Return if vote to kick players is enabled"""
        async with self._get_connection() as conn:
            result = await conn.get_vote_kick_enabled()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = VoteKickState(state=result)  # type: ignore
        except ValueError:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def enable_vote_kick(self, output: MutableSequence | None = None) -> bool:
        """Enable the vote to kick players feature"""
        async with self._get_connection() as conn:
            result = await conn.enable_vote_kick()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def disable_vote_kick(self, output: MutableSequence | None = None) -> bool:
        """Disable the vote to kick players feature"""
        async with self._get_connection() as conn:
            result = await conn.disable_vote_kick()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    @staticmethod
    def _parse_vote_kick_thresholds(
        raw_thresholds: str,
    ) -> list[VoteKickThreshold]:
        values = raw_thresholds.split(",")
        thresholds: list[VoteKickThreshold] = []
        for player, vote in zip(values[0::2], values[1::2]):
            thresholds.append(
                VoteKickThreshold(player_count=player, votes_required=vote)  # type: ignore
            )

        return thresholds

    async def get_vote_kick_thresholds(
        self, output: MutableSequence | None = None
    ) -> list[VoteKickThreshold]:
        """Return the required number of votes to remove from the server in threshold pairs"""
        async with self._get_connection() as conn:
            result = await conn.get_vote_kick_thresholds()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = self._parse_vote_kick_thresholds(result)
            if output is not None:
                output.append(validated_result)
            return validated_result
        except ValueError:
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)

    @staticmethod
    def _convert_vote_kick_thresholds(
        thresholds: Iterable[tuple[int, int]] | Iterable[VoteKickThreshold] | str
    ) -> str:
        if thresholds is None or thresholds == "":
            raise ValueError(
                "Vote kick thresholds must be pairs in the form (player count, votes required), received no pairs"
            )

        raw_thresholds: list[int] = []
        if isinstance(thresholds, str):
            split_thresholds = thresholds.split(",")
            raw_thresholds = [int(threshhold) for threshhold in split_thresholds]
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

        if any(threshold < 0 for threshold in raw_thresholds) or any(
            not isinstance(threshold, int) for threshold in raw_thresholds
        ):
            raise ValueError("Vote kick threshholds must be positive integers")

        if any(threshold > 50 for threshold in raw_thresholds):
            raise ValueError("Thresholds can never be greater than 50")

        return ",".join(str(threshold) for threshold in raw_thresholds)

    async def set_vote_kick_thresholds(
        self,
        thresholds: Iterable[tuple[int, int]] | Iterable[VoteKickThreshold] | str,
        output: MutableSequence | None = None,
    ) -> bool:
        """Set vote kick threshold pairs, the first entry must be for 0 players

        Args
            threshold_pairs: A comma separated list in the form: players, votes required for instance 0,1,10,5
                means when 10 players are on, 5 votes are required to remove a player or a list of VoteKickThreshold
        """
        validated_thresholds = self._convert_vote_kick_thresholds(thresholds)
        async with self._get_connection() as conn:
            result = await conn.set_vote_kick_thresholds(
                threshold_pairs=validated_thresholds
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            logger.error(f"set_vote_kick_thresholds({validated_thresholds})={result}")
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def clear_vote_kick_thresholds(
        self,
        output: MutableSequence | None = None,
    ) -> bool:
        """Clear vote kick threshold pairs

        Removes all the threshold pairs, the game server does not appear to have defaults
        """
        async with self._get_connection() as conn:
            result = await conn.clear_vote_kick_thresholds()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def get_censored_words(
        self,
        output: MutableSequence | None = None,
    ) -> list[CensoredWord]:
        """Return a list of all words that will be censored in game chat"""
        async with self._get_connection() as conn:
            result = await conn.get_censored_words()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        validated_result = [
            CensoredWord(word=word) for word in AsyncRcon._from_hll_list(result)
        ]

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def censor_words(
        self, words: Iterable[str], output: MutableSequence | None = None
    ) -> bool:
        """Add words to the list of words censored in game chat"""
        raw_words = AsyncRcon._to_hll_list(words)
        async with self._get_connection() as conn:
            result = await conn.censor_words(words=raw_words)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result

    async def uncensor_words(
        self, words: Iterable[str], output: MutableSequence | None = None
    ) -> bool:
        """Remove words from the list of words censored in game chat"""
        raw_words = AsyncRcon._to_hll_list(words)
        async with self._get_connection() as conn:
            result = await conn.uncensor_words(words=raw_words)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(constants.INVALID_GAME_SERVER_RESPONSE_ERROR_MSG)
        else:
            validated_result = result == constants.SUCCESS_RESPONSE

        if output is not None:
            output.append(validated_result)

        return validated_result
