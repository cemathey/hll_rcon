from datetime import datetime, timedelta
from typing import TypeAlias

import pydantic

from async_hll_rcon import constants


class IntegerGreaterOrEqualToOne(pydantic.BaseModel):
    value: pydantic.conint(ge=1)  # type: ignore


class ServerNameType(pydantic.BaseModel):
    """The servers name"""

    name: str


class MaxQueueSizeType(pydantic.BaseModel):
    """The maximum number of players that can queue to join"""

    size: int


class NumVipSlotsType(pydantic.BaseModel):
    """The number of reserved VIP slots"""

    count: int


class TemporaryBanType(pydantic.BaseModel):
    """Represents HLL's format for a temporary ban"""

    steam_id_64: str
    player_name: str | None
    duration_hours: int
    timestamp: datetime
    reason: str | None
    admin: str | None

    @staticmethod
    def temp_ban_log_to_str(ban_log: "TemporaryBanType") -> str:
        """Convert to HLL ban log format"""
        # 76561198004123456 : banned for 2 hours on 2023.03.06-13.44.32

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


class InvalidTempBanType(pydantic.BaseModel):
    """As of HLL v1.13.0.815373 it's possible for the game server to send back ban logs missing steam IDs"""

    steam_id_64: str | None
    player_name: str | None
    duration_hours: int
    timestamp: datetime
    reason: str | None
    admin: str | None


class PermanentBanType(pydantic.BaseModel):
    """Represents HLL's format for a permanent ban"""

    steam_id_64: str
    player_name: str | None
    timestamp: datetime
    reason: str | None
    admin: str | None

    @staticmethod
    def perma_ban_log_to_str(ban_log: "PermanentBanType") -> str:
        """Convert to HLL ban log format"""

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


class VoteKickThresholdType(pydantic.BaseModel):
    """A player count and required votes threshold"""

    player_count: int
    votes_required: int


class HighPingLimitType(pydantic.BaseModel):
    """The maximum ping a player can have before being kicked"""

    limit: pydantic.conint(ge=0)  # type: ignore


class VoteKickStateType(pydantic.BaseModel):
    """Whether vote kicks are turned on"""

    state: bool


class TeamSwitchCoolDownType(pydantic.BaseModel):
    """The minimum time in minutes before a player can switch teams"""

    cooldown: pydantic.conint(ge=0)  # type: ignore


class AutoBalanceStateType(pydantic.BaseModel):
    """Whether the auto balance (team size enforcement) is enabled"""

    state: bool


class AutoBalanceThresholdType(pydantic.BaseModel):
    """The maximum allowed difference in team sizes for players joining a team"""

    threshold: pydantic.conint(ge=0)  # type: ignore


class IdleKickTimeType(pydantic.BaseModel):
    """The time in minutes before the server kicks an idle player"""

    kick_time: pydantic.conint(ge=0)  # type: ignore


class ServerPlayerSlotsType(pydantic.BaseModel):
    """The current and max number of players"""

    current_players: int
    max_players: int


class GameStateType(pydantic.BaseModel):
    """The result of the GameState command showing"""

    allied_players: int
    axis_players: int
    allied_score: int
    axis_score: int
    remaining_time: timedelta
    current_map: str
    next_map: str


class CensoredWordType(pydantic.BaseModel):
    """A word that is censored in game chat (replaced by *)"""

    word: str


class MapType(pydantic.BaseModel):
    """A map name"""

    name: str


class AvailableMapsType(pydantic.BaseModel):
    """All of the available maps as returned by the game server"""

    maps: list[MapType]


class MapRotationType(pydantic.BaseModel):
    """A collection of map names"""

    maps: list[MapType]


class PlayerNameType(pydantic.BaseModel):
    """A player name as returned from the game server"""

    name: str


class SteamIdType(pydantic.BaseModel):
    """A string representation of a steam_id_64"""

    steam_id_64: str


class AdminGroupType(pydantic.BaseModel):
    """A HLL console role (owner, senior, junior, spectator)"""

    role: str

    @pydantic.validator("role")
    def valid_admin_role(cls, v):
        if v not in constants.VALID_ADMIN_ROLES:
            raise ValueError(f"{v=} not in {constants.VALID_ADMIN_ROLES=}")
        return v


class AdminIdType(pydantic.BaseModel):
    """The steam id, name and role of a HLL admin"""

    steam_id_64: SteamIdType
    name: PlayerNameType
    role: AdminGroupType


class VipIdType(pydantic.BaseModel):
    """The steam ID and free form text name of a server VIP"""

    steam_id_64: SteamIdType
    name: str


class ScoreType(pydantic.BaseModel):
    """A players score as returned by the PlayerInfo command"""

    kills: int
    deaths: int
    combat: int
    offensive: int
    defensive: int
    support: int


class SquadType(pydantic.BaseModel):
    """A players squad id and name as returned by the PlayerInfo command"""

    unit_id: int
    unit_name: str


class PlayerInfoType(pydantic.BaseModel):
    """A players metadata as returned by the PlayerInfo command"""

    player_name: str
    steam_id_64: str
    team: str | None
    role: str
    loadout: str | None
    unit: SquadType | None
    score: ScoreType
    level: int


class LogTimeStampType(pydantic.BaseModel):
    """The absolute and relative timestamps returned in a game server log line"""

    absolute_timestamp: datetime
    relative_timestamp: timedelta


class KillLogType(pydantic.BaseModel):
    """A game server log line for player kill events"""

    steam_id_64: str
    player_name: str
    player_team: str
    victim_steam_id_64: str
    victim_player_name: str
    victim_team: str
    weapon: str
    time: LogTimeStampType


class TeamKillLogType(pydantic.BaseModel):
    """A game server log line for player team kill events"""

    steam_id_64: str
    player_name: str
    player_team: str
    victim_steam_id_64: str
    victim_player_name: str
    victim_team: str
    weapon: str
    time: LogTimeStampType


class ChatLogType(pydantic.BaseModel):
    """A game server log line for text chat"""

    steam_id_64: str
    player_name: str
    player_team: str
    scope: str
    content: str
    time: LogTimeStampType


class ConnectLogType(pydantic.BaseModel):
    """A game server log line for a player connect event"""

    steam_id_64: str
    player_name: str
    time: LogTimeStampType


class DisconnectLogType(pydantic.BaseModel):
    """A game server log line for a player disconnect event"""

    steam_id_64: str
    player_name: str
    time: LogTimeStampType


class TeamSwitchLogType(pydantic.BaseModel):
    """A game server log line for a player switching teams (axis, allied or none)"""

    player_name: str
    from_team: str
    to_team: str
    time: LogTimeStampType


class KickLogType(pydantic.BaseModel):
    """A game server log line for a player being kicked from the game"""

    player_name: str
    # idle eac host temp perma
    kick_type: str
    reason: str | None
    time: LogTimeStampType


class BanLogType(pydantic.BaseModel):
    """A game server log line for a player being banned from the game"""

    player_name: str
    # Temporary or permanent
    # TODO: create types for perma/temp
    ban_type: str
    ban_duration_hours: int | None
    reason: str
    time: LogTimeStampType


class MatchStartLogType(pydantic.BaseModel):
    """A game server log line for the start of a match"""

    map_name: str
    game_mode: str
    time: LogTimeStampType


class MatchEndLogType(pydantic.BaseModel):
    """A game server log line for the end of a match"""

    map_name: str
    game_mode: str
    allied_score: int
    axis_score: int
    time: LogTimeStampType


class EnteredAdminCamLogType(pydantic.BaseModel):
    """A game server log line for a player entering admin cam"""

    steam_id_64: str
    player_name: str
    time: LogTimeStampType


class ExitedAdminCamLogType(pydantic.BaseModel):
    """A game server log line for a player exiting admin cam"""

    steam_id_64: str
    player_name: str
    time: LogTimeStampType


class VoteKickStartedLogType(pydantic.BaseModel):
    """A game server log line for a vote kick being initiated"""

    player_name: str
    victim_player_name: str
    vote_type: str
    vote_id: int
    time: LogTimeStampType


class VoteKickPlayerVoteLogType(pydantic.BaseModel):
    """A game server log line for a player voting on a vote kick"""

    player_name: str
    vote_type: str
    vote_id: int
    time: LogTimeStampType


class VoteKickCompletedStatusType(pydantic.BaseModel):
    """A game server log line for the status of a completed vote kick"""

    vote_result: str
    vote_id: int
    time: LogTimeStampType


class VoteKickExpiredLogType(pydantic.BaseModel):
    """A game server log line for the expiration of a vote kick"""

    vote_id: int
    time: LogTimeStampType


class VoteKickResultsLogType(pydantic.BaseModel):
    """A game server log line for the result of a passed vote kick"""

    victim_player_name: str
    for_votes: int
    against_votes: int
    votes_required: int
    time: LogTimeStampType

    @property
    def total_votes(self):
        return self.for_votes + self.against_votes


class MessagedPlayerLogType(pydantic.BaseModel):
    """A game server log line for a message sent to a player"""

    steam_id_64: str
    player_name: str
    message: str
    time: LogTimeStampType


GameLogType: TypeAlias = list[
    BanLogType
    | ChatLogType
    | ConnectLogType
    | DisconnectLogType
    | EnteredAdminCamLogType
    | ExitedAdminCamLogType
    | KickLogType
    | KillLogType
    | MatchEndLogType
    | MatchStartLogType
    | MessagedPlayerLogType
    | TeamKillLogType
    | TeamSwitchLogType
    | VoteKickExpiredLogType
    | VoteKickCompletedStatusType
    | VoteKickPlayerVoteLogType
    | VoteKickResultsLogType
    | VoteKickStartedLogType
    | None
]
