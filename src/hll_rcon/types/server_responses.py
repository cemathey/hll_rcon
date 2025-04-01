"""Fully validated game server responses"""

from hll_rcon.types.constants import Platform, Teams
from pydantic import BaseModel, Field, field_validator
from typing import TypedDict, Iterable
from loguru import logger


class RconResponse(BaseModel):
    """The format the game server returns from a RCON request"""

    status_code: int = Field(validation_alias="statusCode")
    status_msg: str = Field(validation_alias="statusMessage")
    version: int = Field(validation_alias="version")
    command: str = Field(validation_alias="name")
    body: str = Field(validation_alias="contentBody")

    class Config:
        populate_by_name = True


class RconCommandResponse(BaseModel):
    """A discoverable RCON command"""

    id: str = Field(validation_alias="iD")
    friendly_name: str = Field(validation_alias="friendlyName")
    is_client_supported: bool = Field(validation_alias="isClientSupported")


class ServerConfig(BaseModel):
    name: str = Field(validation_alias="serverName")
    build_number: str = Field(validation_alias="buildNumber")
    revision: str = Field(validation_alias="buildRevision")
    supported_platforms: set[Platform] = Field(validation_alias="supportedPlatforms")

    @field_validator("supported_platforms", mode="before")
    @classmethod
    def validate_platform(cls, vs: Iterable[str]):
        return [Platform(v.lower()) for v in vs]


class SessionInfo(BaseModel):
    name: str = Field(validation_alias="serverName")
    # TODO: layer parsing
    map_name: str = Field(validation_alias="mapName")
    game_mode: str = Field(validation_alias="gameMode")
    player_count: int = Field(validation_alias="playerCount")
    max_player_count: int = Field(validation_alias="maxPlayerCount")
    vip_queued_players: int = Field(validation_alias="vIPQueueCount")
    queued_players: int = Field(validation_alias="queueCount")
    max_queue_count: int = Field(validation_alias="maxQueueCount")
    max_vip_queue_count: int = Field(validation_alias="maxVIPQueueCount")


class Map(BaseModel):
    name: str
    game_mode: str = Field(validation_alias="gameMode")
    time_of_day: str = Field(validation_alias="timeOfDay")
    id: str = Field(validation_alias="iD")
    index: int = Field(validation_alias="position")


class MapRotation(BaseModel):
    maps: list[Map]


class Position(BaseModel):
    x: float
    y: float
    z: float

    # TODO: add helper methods for in/out of bounds which sector; etc.


class PlayerScore(BaseModel):
    kills: int
    deaths: int
    combat: int = Field(validation_alias="cOMBAT")
    offense: int
    defense: int
    support: int


class Player(BaseModel):
    name: str
    clan_tag: str = Field(validation_alias="clanTag")
    player_id: str = Field(validation_alias="iD")
    epic_id: str = Field(validation_alias="eOSId")
    platform: Platform = Field()
    level: int
    team_id: Teams = Field(validation_alias="team")
    # TODO: make this an Enum
    squad: str = Field(validation_alias="platoon")
    # TODO: make this an Enum
    loadout: str
    # score: PlayerScoreResponse
    position: Position = Field(validation_alias="worldPosition")

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str):
        return Platform(v.lower())


class PlayersResponse(BaseModel):
    players: dict[str, Player]
