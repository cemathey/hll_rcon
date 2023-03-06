from dataclasses import dataclass
from datetime import datetime

import pydantic

SUCCESS = "SUCCESS"
FAIL = "FAIL"
FAIL_MAP_REMOVAL = "Requested map name was not found"

VALID_ADMIN_ROLES = ("owner", "senior", "junior", "spectator")

HLL_BOOL_ENABLED = "on"
HLL_BOOL_DISABLED = "off"


@dataclass()
class TempBanType:
    steam_id_64: str
    player_name: str | None
    duration_hours: int
    timestamp: datetime
    reason: str
    admin: str


@dataclass()
class PermanentBanType:
    steam_id_64: str
    player_name: str | None
    timestamp: datetime
    reason: str
    admin: str


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
