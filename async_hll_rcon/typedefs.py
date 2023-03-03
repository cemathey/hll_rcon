from dataclasses import dataclass
from datetime import datetime


@dataclass()
class BanType:
    steam_id_64: str
    player_name: str
    duration_hours: int
    timestamp: datetime
    reason: str
    admin: str
