from dataclasses import dataclass
from datetime import datetime, timedelta

import pydantic

from async_hll_rcon import constants

SUCCESS = "SUCCESS"
FAIL = "FAIL"
FAIL_MAP_REMOVAL = "Requested map name was not found"

VALID_ADMIN_ROLES = ("owner", "senior", "junior", "spectator")

HLL_BOOL_ENABLED = "on"
HLL_BOOL_DISABLED = "off"


@dataclass()
class TemporaryBanType:
    steam_id_64: str
    player_name: str | None
    duration_hours: int
    timestamp: datetime
    reason: str | None
    admin: str | None

    @staticmethod
    def temp_ban_log_to_str(ban_log: "TemporaryBanType") -> str:
        # 76561198004895814 : banned for 2 hours on 2023.03.06-13.44.32

        if ban_log.player_name is not None and ban_log.player_name != "":
            player_name = f' nickname "{ban_log.player_name}"'
        else:
            player_name = ""

        timestamp = ban_log.timestamp.strftime("%Y.%m.%d-%H.%M.%S")

        if ban_log.reason is not None:
            reason = f" for {ban_log.reason}"
        else:
            reason = ""

        if ban_log.admin is not None:
            admin = f" by {ban_log.admin}"
        else:
            admin = ""

        return f"{ban_log.steam_id_64} :{player_name} banned for {ban_log.duration_hours} hours on {timestamp}{reason}{admin}"

    def __str__(self) -> str:
        return self.temp_ban_log_to_str(self)


@dataclass()
class InvalidTempBanType:
    """As of v1.13.0.815373 it's possible for the game server to send back ban logs missing steam IDs"""

    steam_id_64: str | None
    player_name: str | None
    duration_hours: int
    timestamp: datetime
    reason: str | None
    admin: str | None


@dataclass()
class PermanentBanType:
    steam_id_64: str
    player_name: str | None
    timestamp: datetime
    reason: str | None
    admin: str | None

    @staticmethod
    def perma_ban_log_to_str(ban_log: "PermanentBanType") -> str:
        # 76561198004895814 : banned for 2 hours on 2023.03.06-13.44.32

        if ban_log.player_name is not None and ban_log.player_name != "":
            player_name = f' nickname "{ban_log.player_name}"'
        else:
            player_name = ""

        timestamp = ban_log.timestamp.strftime("%Y.%m.%d-%H.%M.%S")

        if ban_log.reason is not None:
            reason = f" for {ban_log.reason}"
        else:
            reason = ""

        if ban_log.admin is not None:
            admin = f" by {ban_log.admin}"
        else:
            admin = ""

        return (
            f"{ban_log.steam_id_64} :{player_name} banned on {timestamp}{reason}{admin}"
        )

    def __str__(self) -> str:
        return self.perma_ban_log_to_str(self)


@dataclass()
class VoteKickThreshold:
    player_count: int
    votes_required: int


class HighPingLimit(pydantic.BaseModel):
    limit: pydantic.conint(ge=0)  # type: ignore


class AutoBalanceEnabled(pydantic.BaseModel):
    enabled: bool


class VoteKickEnabled(pydantic.BaseModel):
    enabled: bool


class TeamSwitchCoolDown(pydantic.BaseModel):
    cooldown: pydantic.conint(ge=0)  # type: ignore


class AutoBalanceThreshold(pydantic.BaseModel):
    threshold: pydantic.conint(ge=0)  # type: ignore


class Amount(pydantic.BaseModel):
    amount: pydantic.conint(ge=1)  # type: ignore


class IntegerGreaterOrEqualToOne(pydantic.BaseModel):
    value: pydantic.conint(ge=1) | None  # type: ignore


class IdleKickTime(pydantic.BaseModel):
    kick_time: pydantic.conint(ge=0)  # type: ignore


class Score(pydantic.BaseModel):
    kills: int
    deaths: int
    combat: int
    offensive: int
    defensive: int
    support: int


class PlayerInfo(pydantic.BaseModel):
    player_name: str
    steam_id_64: str
    team: str | None
    role: str
    score: Score
    level: int


class LogTimeStamp(pydantic.BaseModel):
    absolute_timestamp: datetime
    relative_timestamp: timedelta


class KillLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    player_team: str
    victim_steam_id_64: str
    victim_player_name: str
    victim_team: str
    weapon: str
    time: LogTimeStamp


class TeamKillLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    player_team: str
    victim_steam_id_64: str
    victim_player_name: str
    victim_team: str
    weapon: str
    time: LogTimeStamp


class ChatLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    player_team: str
    scope: str
    content: str
    time: LogTimeStamp


class ConnectLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    time: LogTimeStamp


class DisconnectLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    time: LogTimeStamp


class TeamSwitchLogType(pydantic.BaseModel):
    player_name: str
    from_team: str
    to_team: str
    time: LogTimeStamp


class KickLogType(pydantic.BaseModel):
    player_name: str
    # idle eac host temp perma
    kick_type: str
    time: LogTimeStamp


class BanLogType(pydantic.BaseModel):
    player_name: str
    # Temporary or permanent
    ban_type: str
    ban_duration_hours: int | None
    reason: str
    time: LogTimeStamp


class MatchStartLogType(pydantic.BaseModel):
    map_name: str
    game_mode: str
    time: LogTimeStamp


class MatchEndLogType(pydantic.BaseModel):
    map_name: str
    game_mode: str
    allied_score: int
    axis_score: int
    time: LogTimeStamp
