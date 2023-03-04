from dataclasses import dataclass
from datetime import datetime


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
