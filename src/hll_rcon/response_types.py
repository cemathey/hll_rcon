"""Models for game server command responses"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TypeAlias

import pydantic

from hll_rcon import constants


class BaseResponse(pydantic.BaseModel):
    timestamp: pydantic.AwareDatetime = pydantic.Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class ServerName(BaseResponse):
    """The servers name"""

    name: str


class MaxQueueSize(BaseResponse):
    """The maximum number of players that can queue to join"""

    size: int


class NumVipSlots(BaseResponse):
    """The number of reserved VIP slots"""

    count: int


class VoteKickThreshold(BaseResponse):
    """A player count and required votes threshold"""

    player_count: int
    votes_required: int


class HighPingLimit(BaseResponse):
    """The maximum ping a player can have before being kicked"""

    limit: pydantic.conint(ge=0)  # type: ignore


class VoteKickState(BaseResponse):
    """Whether vote kicks are turned on"""

    state: bool


class TeamSwitchCoolDown(BaseResponse):
    """The minimum time in minutes before a player can switch teams"""

    cooldown: pydantic.conint(ge=0)  # type: ignore


class AutoBalanceState(BaseResponse):
    """Whether the auto balance (team size enforcement) is enabled"""

    state: bool


class AutoBalanceThreshold(BaseResponse):
    """The maximum allowed difference in team sizes for players joining a team"""

    threshold: pydantic.conint(ge=0)  # type: ignore


class IdleKickTime(BaseResponse):
    """The time in minutes before the server kicks an idle player"""

    kick_time: pydantic.conint(ge=0)  # type: ignore


class ServerPlayerSlots(BaseResponse):
    """The current and max number of players"""

    current_players: int
    max_players: int


class TemporaryBan(BaseResponse):
    """Represents HLL's format for a temporary ban"""

    player_id: str
    player_name: str | None
    duration_hours: int
    ban_timestamp: datetime
    reason: str | None
    admin: str | None

    @staticmethod
    def temp_ban_log_to_str(ban_log: "TemporaryBan") -> str:
        """Convert to HLL ban log format"""
        # 76561198004123456 : banned for 2 hours on 2023.03.06-13.44.32

        if ban_log.player_name is not None and ban_log.player_name != "":
            player_name = f' nickname "{ban_log.player_name}"'
        else:
            player_name = ""

        timestamp = ban_log.ban_timestamp.strftime("%Y.%m.%d-%H.%M.%S")

        if ban_log.reason is not None:
            reason = f" for {ban_log.reason}"
        else:
            reason = ""

        if ban_log.admin is not None:
            admin = f" by {ban_log.admin}"
        else:
            admin = ""

        return f"{ban_log.player_id} :{player_name} banned for {ban_log.duration_hours} hours on {timestamp}{reason}{admin}"

    def __str__(self) -> str:
        return self.temp_ban_log_to_str(self)


class InvalidTempBan(BaseResponse):
    """As of HLL v1.13.0.815373 it's possible for the game server to send back ban logs missing steam IDs"""

    player_id: str | None
    player_name: str | None
    duration_hours: int
    ban_timestamp: datetime
    reason: str | None
    admin: str | None


class PermanentBan(BaseResponse):
    """Represents HLL's format for a permanent ban"""

    player_id: str
    player_name: str | None
    ban_timestamp: datetime
    reason: str | None
    admin: str | None

    @staticmethod
    def perma_ban_log_to_str(ban_log: "PermanentBan") -> str:
        """Convert to HLL ban log format"""

        if ban_log.player_name is not None and ban_log.player_name != "":
            player_name = f' nickname "{ban_log.player_name}"'
        else:
            player_name = ""

        timestamp = ban_log.ban_timestamp.strftime("%Y.%m.%d-%H.%M.%S")

        if ban_log.reason is not None:
            reason = f" for {ban_log.reason}"
        else:
            reason = ""

        if ban_log.admin is not None:
            admin = f" by {ban_log.admin}"
        else:
            admin = ""

        return (
            f"{ban_log.player_id} :{player_name} banned on {timestamp}{reason}{admin}"
        )

    def __str__(self) -> str:
        return self.perma_ban_log_to_str(self)


class GameState(BaseResponse):
    """The result of the GameState command showing"""

    allied_players: int
    axis_players: int
    allied_score: int
    axis_score: int
    remaining_time: timedelta
    current_map: str
    next_map: str


class CensoredWord(BaseResponse):
    """A word that is censored in game chat (replaced by *)"""

    word: str


class AvailableMaps(BaseResponse):
    """All of the available maps as returned by the game server"""

    # TODO: change this to layers
    maps: list[str]


class MapRotation(BaseResponse):
    """A collection of map names"""

    # TODO: change this to layers
    maps: list[str]


class AdminGroup(BaseResponse):
    """A HLL console role (owner, senior, junior, spectator)"""

    role: str

    @pydantic.field_validator("role")
    def valid_admin_role(cls, v):
        if v not in constants.VALID_ADMIN_ROLES:
            raise ValueError(f"{v=} not in {constants.VALID_ADMIN_ROLES=}")
        return v


class AdminId(BaseResponse):
    """The steam id, name and role of a HLL admin"""

    player_id: str
    name: str
    role: AdminGroup


class VipId(BaseResponse):
    """The steam ID and free form text name of a server VIP"""

    player_id: str
    name: str


class PlayerScore(BaseResponse):
    """A players score as returned by the PlayerInfo command"""

    kills: int = pydantic.Field(default=0)
    deaths: int = pydantic.Field(default=0)
    combat: int = pydantic.Field(default=0)
    offensive: int = pydantic.Field(default=0)
    defensive: int = pydantic.Field(default=0)
    support: int = pydantic.Field(default=0)


class Squad(BaseResponse):
    """A players squad id and name as returned by the PlayerInfo command"""

    unit_id: int
    unit_name: str


class Player(BaseResponse):
    player_name: str
    player_id: str


class PlayerInfo(BaseResponse):
    """A players metadata as returned by the PlayerInfo command"""

    player_name: str
    player_id: str
    team: str | None
    role: str
    loadout: str | None
    unit: Squad | None
    score: PlayerScore
    level: int
