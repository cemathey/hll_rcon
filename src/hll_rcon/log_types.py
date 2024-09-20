"""Models for game server logs"""

from datetime import datetime, timedelta
from enum import Enum
from typing import TypeAlias

import pydantic

from hll_rcon import constants


class GameServerCredentials(pydantic.BaseModel):
    host_ip: pydantic.IPvAnyAddress
    # port 0 is technically a port but will never occur
    host_port: pydantic.conint(ge=1)  # type: ignore
    password: str


class LogTimeStamp(pydantic.BaseModel):
    """The absolute and relative timestamps returned in a game server log line"""

    absolute_timestamp: pydantic.AwareDatetime
    relative_timestamp: timedelta


class BaseLogModel(pydantic.BaseModel):
    time: LogTimeStamp
    id: bytes


class KillLog(BaseLogModel):
    """A game server log line for player kill events"""

    player_id: str
    player_name: str
    player_team: str
    victim_player_id: str
    victim_player_name: str
    victim_team: str
    weapon: str


class TeamKillLog(BaseLogModel):
    """A game server log line for player team kill events"""

    player_id: str
    player_name: str
    player_team: str
    victim_player_id: str
    victim_player_name: str
    victim_team: str
    weapon: str


class ChatLog(BaseLogModel):
    """A game server log line for text chat"""

    player_id: str
    player_name: str
    player_team: str
    scope: str
    content: str


class ConnectLog(BaseLogModel):
    """A game server log line for a player connect event"""

    player_id: str
    player_name: str


class DisconnectLog(BaseLogModel):
    """A game server log line for a player disconnect event"""

    player_id: str
    player_name: str


class TeamSwitchLog(BaseLogModel):
    """A game server log line for a player switching teams (axis, allied or none)"""

    player_name: str
    from_team: str
    to_team: str


class KickLog(BaseLogModel):
    """A game server log line for a player being kicked from the game"""

    player_name: str
    # idle eac host temp perma
    kick_type: str
    reason: str | None


class BanLogBan(Enum):
    TEMPORARY_BAN = 1
    PERMANENT_BAN = 2


class BanLog(BaseLogModel):
    """A game server log line for a player being banned from the game"""

    player_name: str
    ban_type: BanLogBan
    ban_duration_hours: int | None
    reason: str


class MatchStartLog(BaseLogModel):
    """A game server log line for the start of a match"""

    map_name: str
    game_mode: str


class MatchEndLog(BaseLogModel):
    """A game server log line for the end of a match"""

    map_name: str
    game_mode: str
    allied_score: int
    axis_score: int


class EnteredAdminCamLog(BaseLogModel):
    """A game server log line for a player entering admin cam"""

    player_id: str
    player_name: str


class ExitedAdminCamLog(BaseLogModel):
    """A game server log line for a player exiting admin cam"""

    player_id: str
    player_name: str


class VoteKickStartedLog(BaseLogModel):
    """A game server log line for a vote kick being initiated"""

    player_name: str
    victim_player_name: str
    vote_type: str
    vote_id: int


class VoteKickPlayerVoteLog(BaseLogModel):
    """A game server log line for a player voting on a vote kick"""

    player_name: str
    vote_type: str
    vote_id: int


class VoteKickCompletedStatusLog(BaseLogModel):
    """A game server log line for the status of a completed vote kick"""

    vote_result: str
    vote_id: int


class VoteKickExpiredLog(BaseLogModel):
    """A game server log line for the expiration of a vote kick"""

    vote_id: int


class VoteKickResultsLog(BaseLogModel):
    """A game server log line for the result of a passed vote kick"""

    victim_player_name: str
    for_votes: int
    against_votes: int
    votes_required: int

    @property
    def total_votes(self):
        return self.for_votes + self.against_votes


class MessagedPlayerLog(BaseLogModel):
    """A game server log line for a message sent to a player"""

    player_id: str
    player_name: str
    message: str


GameLogType: TypeAlias = (
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
)
