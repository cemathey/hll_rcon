import inspect
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator, Iterable

import trio
from dateutil import parser
from loguru import logger

from async_hll_rcon import constants
from async_hll_rcon.connection import HllConnection
from async_hll_rcon.typedefs import (
    AdminCamLogType,
    AutoBalanceEnabledType,
    AutoBalanceThresholdType,
    BanLogType,
    ChatLogType,
    ConnectLogType,
    DisconnectLogType,
    HighPingLimitType,
    IdleKickTimeType,
    IntegerGreaterOrEqualToOne,
    InvalidTempBanType,
    KickLogType,
    KillLogType,
    LogTimeStampType,
    MatchEndLogType,
    MatchStartLogType,
    MessagedPlayerLogType,
    PermanentBanType,
    PlayerInfoType,
    ScoreType,
    TeamKillLogType,
    TeamSwitchCoolDownType,
    TeamSwitchLogType,
    TemporaryBanType,
    VoteKickEnabledType,
    VoteKickExpiredLogType,
    VoteKickPassedLogType,
    VoteKickPlayerVoteLogType,
    VoteKickResultsLogType,
    VoteKickStartedLogType,
    VoteKickThresholdType,
)


class AsyncRcon:
    """Represents a high level RCON pool of game server connections and returns processed results"""

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
    # _admin_cam_pattern = r"\[(.*)\s{1}\((\d{17})\)\]"
    _admin_cam_pattern = r"Player \[(.*) \((\d{17})\)\] (Entered|Left) Admin Camera"
    _match_start_pattern = re.compile(r"MATCH START (.*) (WARFARE|OFFENSIVE)")
    _match_end_pattern = re.compile(
        r"MATCH ENDED `(.*) (WARFARE|OFFENSIVE)` ALLIED \((\d) - (\d)"
    )
    _message_player_pattern = re.compile(
        r"MESSAGE: player \[(.+)\((\d+)\)\], content \[(.+)\]", re.DOTALL
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
        self._ip_addr = ip_addr
        self._port = int(port)
        self._password = password
        self._receive_timeout = receive_timeout
        self._tcp_timeout = tcp_timeout
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
                self._ip_addr,
                self._port,
                self._password,
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
        """Convert a game server tab delimited result string to a native list

        Raises
            ValueError: if the parsed number of items is less than the indicated number of items,
                does not raise if extra items are present because some commands such as get_temp_bans
                return results with empty entries and others include trailing values so it is difficult
                to definitively establish how many elements are in a list
        """
        # raw_list = raw_list.strip()

        expected_length, *items = raw_list.split("\t")
        expected_length = int(expected_length)

        if len(items) < expected_length:
            logger.debug(f"{expected_length=}")
            logger.debug(f"{len(items)=}")
            logger.debug(f"{items=}")
            if len(items) == 1 and not items[0]:
                return []

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

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def get_num_vip_slots(self):
        async with self._get_connection() as conn:
            result = await conn.get_num_vip_slots()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def set_num_vip_slots(self, amount: int):
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

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def clear_broadcast_message(self):
        async with self._get_connection() as conn:
            result = await conn.clear_broadcast_message()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

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
        | AdminCamLogType
        | VoteKickPlayerVoteLogType
        | VoteKickPassedLogType
        | VoteKickStartedLogType
        | VoteKickResultsLogType
        | MessagedPlayerLogType
        | VoteKickExpiredLogType
        | None
    ):
        time = LogTimeStampType(
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

                    return KickLogType(
                        player_name=player_name,
                        kick_type=removal_type,
                        reason=removal_reason,
                        time=time,
                    )
                    logger.warning(f"{k}")
                    return k
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
                        ban_type = constants.TEMPORARY_BAN
                    else:
                        ban_type = constants.PERMANENT_BAN

                    if removal_reason is None or removal_reason == "":
                        # logger.error(
                        #     f"{player_name=} {ban_type=} {ban_duration=} {removal_reason=}"
                        # )
                        logger.error(f"{raw_log=}")

                    return BanLogType(
                        player_name=player_name,
                        ban_type=ban_type,
                        ban_duration_hours=ban_duration,
                        reason=removal_reason,
                        time=time,
                    )
                    logger.warning(f"{b}")
                    return b
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("MATCH"):
            if match := re.match(AsyncRcon._match_start_pattern, raw_log):
                map_name, game_mode = match.groups()
                return MatchStartLogType(
                    map_name=map_name, game_mode=game_mode, time=time
                )
            elif match := re.match(AsyncRcon._match_end_pattern, raw_log):
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
        elif raw_log.startswith("Player"):
            if match := re.match(AsyncRcon._admin_cam_pattern, raw_log):
                player_name, steam_id_64, entered_exited = match.groups()

                if entered_exited == "Entered":
                    kind = constants.ADMIN_CAM_ENTERED
                elif entered_exited == "Left":
                    kind = constants.ADMIN_CAM_LEFT
                else:
                    raise ValueError(f"invalid {entered_exited=} {raw_log=}")

                return AdminCamLogType(
                    steam_id_64=steam_id_64,
                    player_name=player_name,
                    kind=kind,
                    time=time,
                )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("VOTESYS"):
            if match := re.match(AsyncRcon._player_voted_pattern, raw_log):
                player_name, vote_type, vote_id = match.groups()
                return VoteKickPlayerVoteLogType(
                    player_name=player_name,
                    vote_type=vote_type,
                    vote_id=int(vote_id),
                    time=time,
                )
            elif match := re.match(AsyncRcon._vote_completed_pattern, raw_log):
                vote_id, vote_result = match.groups()
                return VoteKickPassedLogType(
                    vote_result=vote_result, vote_id=int(vote_id), time=time
                )
            elif match := re.match(AsyncRcon._vote_expired_pattern, raw_log):
                vote_id = match.groups()[0]
                return VoteKickExpiredLogType(vote_id=int(vote_id), time=time)
            elif match := re.match(AsyncRcon._vote_started_pattern, raw_log):
                player_name, vote_type, victim_player_name, vote_id = match.groups()
                return VoteKickStartedLogType(
                    player_name=player_name,
                    victim_player_name=victim_player_name,
                    vote_type=vote_type,
                    vote_id=int(vote_id),
                    time=time,
                )
            elif match := re.match(AsyncRcon._vote_results_pattern, raw_log):
                (
                    victim_player_name,
                    for_votes,
                    votes_required,
                    against_votes,
                ) = match.groups()
                return VoteKickResultsLogType(
                    victim_player_name=victim_player_name,
                    for_votes=int(for_votes),
                    against_votes=int(against_votes),
                    votes_required=int(votes_required),
                    time=time,
                )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        elif raw_log.startswith("MESSAGE"):
            if match := re.match(AsyncRcon._message_player_pattern, raw_log):
                player_name, steam_id_64, message = match.groups()
                return MessagedPlayerLogType(
                    steam_id_64=steam_id_64,
                    player_name=player_name,
                    message=message,
                    time=time,
                )
            else:
                raise ValueError(f"Unable to parse `{raw_log}`")
        else:
            logger.error(f"Unable to parse `{raw_log}` (fell through)")
            # raise ValueError(f"Unable to parse `{raw_log}` (fell through)")

    _log_split_pattern = re.compile(
        r"^\[([\d:.]+ (?:hours|min|sec|ms)) \((\d+)\)\]", re.MULTILINE
    )

    @staticmethod
    def split_raw_log_lines(
        raw_logs: str,
    ) -> Generator[tuple[str, str, str], None, None]:
        """Split raw game server logs into the line, relative time and absolute UTC timestamp"""
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

    async def get_game_logs(self, minutes: int, filter: str | None = None):
        async with self._get_connection() as conn:
            result = await conn.get_game_logs(minutes=minutes, filter=filter)
            # logger.debug(
            #     f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            # )

        if result == "EMPTY":
            return []
        else:
            logs = []
            for raw_log, relative_time, absolute_time in AsyncRcon.split_raw_log_lines(
                result
            ):
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
        if result not in (
            constants.SUCCESS_RESPONSE,
            constants.FAIL_MAP_REMOVAL_RESPONSE,
        ):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def remove_map_from_rotation(self, name: str, ordinal: int | None = 1):
        async with self._get_connection() as conn:
            result = await conn.remove_map_from_rotation(name=name, ordinal=ordinal)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (
            constants.SUCCESS_RESPONSE,
            constants.FAIL_MAP_REMOVAL_RESPONSE,
        ):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def set_current_map(self, name: str, ordinal: int | None = 1) -> bool:
        async with self._get_connection() as conn:
            result = await conn.set_current_map(name=name, ordinal=ordinal)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def get_players(self):
        async with self._get_connection() as conn:
            result = await conn.get_players()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_player_steam_ids(self):
        # TODO: format result
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

            if not all(group in constants.VALID_ADMIN_ROLES for group in groups):
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

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def remove_admin(self, steam_id_64: str):
        async with self._get_connection() as conn:
            result = await conn.remove_admin(steam_id_64=steam_id_64)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def get_vip_ids(self):
        async with self._get_connection() as conn:
            result = await conn.get_vip_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )
            return AsyncRcon.from_hll_list(result)

    @staticmethod
    def parse_player_info(raw_player_info: str) -> PlayerInfoType:
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

        processed_score = ScoreType(
            kills=int(kills),
            deaths=int(deaths),
            combat=scores["C"],
            offensive=scores["O"],
            defensive=scores["D"],
            support=scores["S"],
        )

        return PlayerInfoType(
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

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def remove_vip(self, steam_id_64: str):
        async with self._get_connection() as conn:
            result = await conn.remove_vip(steam_id_64=steam_id_64)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

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

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def punish_player(self, player_name: str, reason: str | None = None):
        async with self._get_connection() as conn:
            result = await conn.punish_player(player_name=player_name, reason=reason)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def switch_player_on_death(self, player_name: str):
        async with self._get_connection() as conn:
            result = await conn.switch_player_on_death(player_name=player_name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def switch_player_now(self, player_name: str):
        async with self._get_connection() as conn:
            result = await conn.switch_player_now(player_name=player_name)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def kick_player(self, player_name: str, reason: str | None = None):
        async with self._get_connection() as conn:
            result = await conn.kick_player(player_name=player_name, reason=reason)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def temp_ban_player(
        self,
        steam_id_64: str | None = None,
        player_name: str | None = None,
        duration_hours: int | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
    ):
        if steam_id_64 is None and player_name is None:
            raise ValueError(f"Must provide at least either a steam ID or player name")

        try:
            args = IntegerGreaterOrEqualToOne(value=duration_hours)
        except ValueError:
            raise ValueError(f"`duration` must be an integer >= 1 or None")

        async with self._get_connection() as conn:
            result = await conn.temp_ban_player(
                steam_id_64=steam_id_64,
                player_name=player_name,
                duration_hours=args.value,
                reason=reason,
                by_admin_name=by_admin_name,
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

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

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

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

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

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

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def get_idle_kick_time(self) -> IdleKickTimeType:
        async with self._get_connection() as conn:
            result = await conn.get_idle_kick_time()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            return IdleKickTimeType(kick_time=result)

    async def set_idle_kick_time(self, threshold_minutes: int) -> bool:
        args = IdleKickTimeType(kick_time=threshold_minutes)

        async with self._get_connection() as conn:
            result = await conn.set_idle_kick_time(threshold_minutes=args.kick_time)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

            if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
                raise ValueError(f"Received an invalid response from the game server")
            else:
                return result == constants.SUCCESS_RESPONSE

    async def get_high_ping_limit(self):
        async with self._get_connection() as conn:
            result = await conn.get_high_ping_limit()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = HighPingLimitType(limit=result)
        except ValueError as e:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        return validated_result.limit

    async def set_high_ping_limit(self, threshold: int):
        try:
            args = HighPingLimitType(limit=threshold)
        except ValueError as e:
            logger.error(f"{threshold=} must be an integer >= 0")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_high_ping_limit(threshold=args.limit)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def disable_high_ping_limit(self):
        async with self._get_connection() as conn:
            result = await conn.disable_high_ping_limit()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def get_team_switch_cooldown(self) -> int:
        async with self._get_connection() as conn:
            result = await conn.get_team_switch_cooldown()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = TeamSwitchCoolDownType(cooldown=result)
        except ValueError as e:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        return validated_result.cooldown

    async def set_team_switch_cooldown(self, cooldown: int):
        try:
            args = TeamSwitchCoolDownType(cooldown=cooldown)
        except ValueError as e:
            logger.error(f"{cooldown=} must be a positive integer")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_team_switch_cooldown(args.cooldown)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def get_auto_balance_enabled(self):
        async with self._get_connection() as conn:
            result = await conn.get_auto_balance_enabled()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = AutoBalanceEnabledType(enabled=result)  # type: ignore
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

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def disable_auto_balance(self):
        async with self._get_connection() as conn:
            result = await conn.disable_auto_balance()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def get_auto_balance_threshold(self):
        async with self._get_connection() as conn:
            result = await conn.get_auto_balance_threshold()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = AutoBalanceThresholdType(threshold=result)  # type: ignore
        except ValueError as e:
            raise ValueError(
                f"Received an invalid response=`{result}` from the game server"
            )

        return validated_result.threshold

    async def set_auto_balance_threshold(self, threshold: int):
        try:
            args = AutoBalanceThresholdType(threshold=threshold)
        except ValueError as e:
            logger.error(f"{threshold=} must be a positive integer")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_auto_balance_threshold(args.threshold)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def get_vote_kick_enabled(self):
        async with self._get_connection() as conn:
            result = await conn.get_vote_kick_enabled()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        try:
            validated_result = VoteKickEnabledType(enabled=result)  # type: ignore
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

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def disable_vote_kick(self):
        async with self._get_connection() as conn:
            result = await conn.disable_vote_kick()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def get_vote_kick_thresholds(self) -> list[VoteKickThresholdType]:
        async with self._get_connection() as conn:
            result = await conn.get_vote_kick_thresholds()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        def parse_vote_kick_threshold(
            raw_thresholds: str,
        ) -> list[VoteKickThresholdType]:
            values = raw_thresholds.split(",")
            thresholds: list[VoteKickThresholdType] = []
            for player, vote in zip(values[0::2], values[1::2]):
                thresholds.append(
                    VoteKickThresholdType(player_count=player, votes_required=vote)  # type: ignore
                )

            return thresholds

        try:
            return parse_vote_kick_threshold(result)
        except ValueError:
            raise ValueError(f"Received an invalid response from the game server")

    @staticmethod
    def convert_vote_kick_thresholds(
        thresholds: Iterable[tuple[int, int]] | Iterable[VoteKickThresholdType] | str
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
                if isinstance(item, VoteKickThresholdType):
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
        self,
        thresholds: Iterable[tuple[int, int]] | Iterable[VoteKickThresholdType] | str,
    ):
        processed_thresholds = self.convert_vote_kick_thresholds(thresholds)
        async with self._get_connection() as conn:
            result = await conn.set_vote_kick_threshold(
                threshold_pairs=processed_thresholds
            )
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        # TODO: report error message from the game server
        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

    async def clear_vote_kick_threshold(self):
        async with self._get_connection() as conn:
            result = await conn.clear_vote_kick_threshold()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

        if result not in (constants.SUCCESS_RESPONSE, constants.FAIL_RESPONSE):
            raise ValueError(f"Received an invalid response from the game server")
        else:
            return result == constants.SUCCESS_RESPONSE

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
