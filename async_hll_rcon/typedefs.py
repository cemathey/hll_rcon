from datetime import datetime, timedelta

import pydantic


class TemporaryBanType(pydantic.BaseModel):
    """Represents a HLL temporary ban log"""

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
    """Represents a HLL permanent ban log"""

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


class VoteKickThresholdType:
    player_count: int
    votes_required: int


class HighPingLimitType(pydantic.BaseModel):
    limit: pydantic.conint(ge=0)  # type: ignore


class AutoBalanceEnabledType(pydantic.BaseModel):
    enabled: bool


class VoteKickEnabledType(pydantic.BaseModel):
    enabled: bool


class TeamSwitchCoolDownType(pydantic.BaseModel):
    cooldown: pydantic.conint(ge=0)  # type: ignore


class AutoBalanceThresholdType(pydantic.BaseModel):
    threshold: pydantic.conint(ge=0)  # type: ignore


class IntegerGreaterOrEqualToOne(pydantic.BaseModel):
    value: pydantic.conint(ge=1)  # type: ignore


class IdleKickTimeType(pydantic.BaseModel):
    kick_time: pydantic.conint(ge=0)  # type: ignore


class ServerPlayerSlotsType(pydantic.BaseModel):
    current_players: int
    max_players: int


class GameStateType(pydantic.BaseModel):
    allied_players: int
    axis_players: int
    allied_score: int
    axis_score: int
    remaining_time: timedelta
    current_map: str
    next_map: str


class AdminIdType(pydantic.BaseModel):
    steam_id_64: str
    role: str
    name: str


class VipIdType(pydantic.BaseModel):
    steam_id_64: str
    name: str


class ScoreType(pydantic.BaseModel):
    kills: int
    deaths: int
    combat: int
    offensive: int
    defensive: int
    support: int


class SquadType(pydantic.BaseModel):
    unit_id: int
    unit_name: str


class PlayerInfoType(pydantic.BaseModel):
    player_name: str
    steam_id_64: str
    team: str | None
    role: str
    loadout: str | None
    unit: SquadType | None
    score: ScoreType
    level: int


class LogTimeStampType(pydantic.BaseModel):
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
    time: LogTimeStampType


class TeamKillLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    player_team: str
    victim_steam_id_64: str
    victim_player_name: str
    victim_team: str
    weapon: str
    time: LogTimeStampType


class ChatLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    player_team: str
    scope: str
    content: str
    time: LogTimeStampType


class ConnectLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    time: LogTimeStampType


class DisconnectLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    time: LogTimeStampType


class TeamSwitchLogType(pydantic.BaseModel):
    player_name: str
    from_team: str
    to_team: str
    time: LogTimeStampType


class KickLogType(pydantic.BaseModel):
    player_name: str
    # idle eac host temp perma
    kick_type: str
    reason: str | None
    time: LogTimeStampType


class BanLogType(pydantic.BaseModel):
    player_name: str
    # Temporary or permanent
    ban_type: str
    ban_duration_hours: int | None
    reason: str
    time: LogTimeStampType


class MatchStartLogType(pydantic.BaseModel):
    map_name: str
    game_mode: str
    time: LogTimeStampType


class MatchEndLogType(pydantic.BaseModel):
    map_name: str
    game_mode: str
    allied_score: int
    axis_score: int
    time: LogTimeStampType


class AdminCamLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    kind: str
    time: LogTimeStampType


class VoteKickStartedLogType(pydantic.BaseModel):
    player_name: str
    victim_player_name: str
    vote_type: str
    vote_id: int
    time: LogTimeStampType


class VoteKickPlayerVoteLogType(pydantic.BaseModel):
    player_name: str
    vote_type: str
    vote_id: int
    time: LogTimeStampType


class VoteKickPassedLogType(pydantic.BaseModel):
    vote_result: str
    vote_id: int
    time: LogTimeStampType


class VoteKickExpiredLogType(pydantic.BaseModel):
    vote_id: int
    time: LogTimeStampType


class VoteKickResultsLogType(pydantic.BaseModel):
    victim_player_name: str
    for_votes: int
    against_votes: int
    votes_required: int
    time: LogTimeStampType

    @property
    def total_votes(self):
        return self.for_votes + self.against_votes


class MessagedPlayerLogType(pydantic.BaseModel):
    steam_id_64: str
    player_name: str
    message: str
    time: LogTimeStampType
