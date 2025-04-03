"""Fully validated game server responses"""

# from hll_rcon.types.constants import Platform, Teams
from pydantic import BaseModel, Field, field_validator
from typing import Iterable, overload, TypeGuard, Literal
from loguru import logger
from hll_rcon.types import constants
import math
from enum import StrEnum


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


class ClientReferenceDataParameter(BaseModel):
    """Models the type of a ClientReferenceData parameter for a discoverable command"""

    type: constants.ClientReferenceDataParameterType
    name: str
    id: str = Field(validation_alias="iD")
    display: str = Field(validation_alias="displayMember")
    value: str = Field(validation_alias="valueMember")

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, v: str) -> constants.ClientReferenceDataParameterType:
        return constants.ClientReferenceDataParameterType(v.lower())

    def as_int(self) -> int:
        return int(self.value)

    def as_text(self) -> str:
        return self.value

    def as_list(self) -> list[str]:
        return self.value.split(",")


class ClientReferenceDataResponse(BaseModel):
    """Models the details of a queried RCON command"""

    name: str
    text: str
    description: str
    parameters: list[ClientReferenceDataParameter] = Field(
        validation_alias="dialogueParameters"
    )


class ServerConfig(BaseModel):
    name: str = Field(validation_alias="serverName")
    build_number: str = Field(validation_alias="buildNumber")
    revision: str = Field(validation_alias="buildRevision")
    supported_platforms: set[constants.Platform] = Field(
        validation_alias="supportedPlatforms"
    )

    @field_validator("supported_platforms", mode="before")
    @classmethod
    def validate_platform(cls, vs: Iterable[str]):
        return [constants.Platform(v.lower()) for v in vs]


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
    """The Unreal Engine x,y,z coordinates of a player relative to the origin (center of the map)

    https://dev.epicgames.com/documentation/en-us/unreal-engine/coordinate-system-and-spaces-in-unreal-engine

    x: Positive values are to the right of the origin
    y: Positive values are to bottom of the origin
    z: Positive values are ascending

    (-1,-1)  |   (1,-1)
             |
             |
    ---------+---------
             |
             |
    (-1, 1)  |   (1, 1)
    """

    x: float
    y: float
    z: float

    # TODO: find a better way to do this so we don't have to store them in each
    # player record
    vertical_map: bool
    hq_sector: int

    def __repr__(self) -> str:
        return f"Position(x={self.x:.2f}, y={self.y:.2f}, z={self.z:.2f}, grid={self.grid})"

    @property
    def normalized_sector(self) -> int:
        """Return a normalized (1 to 5) distance from their HQ sector

        This returns a value from 1 to 5 regardless of the map orientation or
        which side of the map the players HQ sector is on so it can be easily
        compared for determining which sector they are in.

        For example if it can be used to enforce remaining in specific sectors
        during seeding; if it returns 4 or 5 they are past the midpoint
        """
        # TODO: update this when we account for skirmish maps
        if self.hq_sector == 1:
            return self.sector
        else:
            return 5 - self.sector + 1

    def in_bounds(self) -> bool:
        """Test if the player is within the playable area of the map"""
        if self.vertical_map:
            max_x, max_y = constants.V_MAX_X, constants.V_MAX_Y
            logger.info(f"{max_x=} {max_y=}")
        else:
            max_x, max_y = constants.H_MAX_X, constants.H_MAX_Y
            logger.info(f"{max_x=} {max_y=}")

        logger.info(f"{abs(self.x)},{abs(self.y)}")
        logger.info(f"{abs(self.x) > max_x},{abs(self.y) > max_y}")
        if abs(self.x) > max_x or abs(self.y) > max_y:
            return False

        return True

    # TODO: use an enum for columns
    @property
    def column(self) -> constants.MapColumns:
        # No bounds checking because it should be impossible to ever leave the map
        if self.vertical_map:
            # Shift the players position so it is only positive and then divide
            # so we get an index from 0-10 to determine their column
            col_index = int((self.x + 100_000) // 20_000)

        else:
            col_index = int((self.x + 600_000) // 20_000)

        col = constants.MAP_COLUMNS[col_index]
        return constants.MapColumns[col]

    @property
    def row(self) -> int:
        if self.vertical_map:
            row_index = int((self.y + 100_000) // 20_000)
            return row_index + 1
        else:
            row_index = int((self.y + 60_000) // 20_000)
            return row_index + 1

    @property
    def grid(self) -> str:
        return f"{self.column}{self.row}"

    @property
    def sector(self) -> int:
        """Return players sector location or -1 for out of bounds

        This is the horizontal or vertical slice of the map that will contain
        a single strongpoint location

        Vertical Map
        1
        2
        3
        4
        5

        Horizontal Map
        12345
        """
        if not self.in_bounds():
            return -1

        if self.vertical_map:
            # 0.5 to 1: 1 1.5 to 2: 2, etc
            return math.ceil(self.row / 2)
        else:
            if self.column in ("A", "B"):
                return 1
            elif self.column in ("C", "D"):
                return 2
            elif self.column in ("E", "F"):
                return 3
            elif self.column in ("G", "H"):
                return 4
            elif self.column in ("I", "J"):
                return 5

        raise ValueError(f"Invalid sector x={self.x},y={self.y}")

    @property
    def zone(self) -> int:
        """Return players zone (objective) location or -1 for out of bounds

        This corresponds to the cap zone for the different sector objectives


        Vertical Map
        01 02 03
        04 05 06
        07 08 09
        10 11 12
        13 14 15


        Horizontal Map
        01 04 07 10 13
        02 05 08 11 14
        03 06 09 12 15
        """
        if not self.in_bounds():
            return -1

        if self.vertical_map:
            if 1 <= self.row <= 2:
                if self.column in ("C", "D"):
                    return 1
                elif self.column in ("E", "F"):
                    return 2
                elif self.column in ("G", "H"):
                    return 3
            elif 3 <= self.row <= 4:
                if self.column in ("C", "D"):
                    return 4
                elif self.column in ("E", "F"):
                    return 5
                elif self.column in ("G", "H"):
                    return 6
            elif 5 <= self.row <= 6:
                if self.column in ("C", "D"):
                    return 7
                elif self.column in ("E", "F"):
                    return 8
                elif self.column in ("G", "H"):
                    return 9
            elif 7 <= self.row <= 8:
                if self.column in ("C", "D"):
                    return 10
                elif self.column in ("E", "F"):
                    return 11
                elif self.column in ("G", "H"):
                    return 12
            elif 7 <= self.row <= 8:
                if self.column in ("C", "D"):
                    return 10
                elif self.column in ("E", "F"):
                    return 11
                elif self.column in ("G", "H"):
                    return 12
            elif 9 <= self.row <= 10:
                if self.column in ("C", "D"):
                    return 13
                elif self.column in ("E", "F"):
                    return 14
                elif self.column in ("G", "H"):
                    return 15
        else:
            if self.column in ("A", "B"):
                if 3 <= self.row <= 4:
                    return 1
                if 5 <= self.row <= 6:
                    return 2
                if 7 <= self.row <= 8:
                    return 3
            if self.column in ("C", "D"):
                if 3 <= self.row <= 4:
                    return 4
                if 5 <= self.row <= 6:
                    return 5
                if 7 <= self.row <= 8:
                    return 6
            if self.column in ("E", "F"):
                if 3 <= self.row <= 4:
                    return 7
                if 5 <= self.row <= 6:
                    return 8
                if 7 <= self.row <= 8:
                    return 9
            if self.column in ("G", "H"):
                if 3 <= self.row <= 4:
                    return 10
                if 5 <= self.row <= 6:
                    return 11
                if 7 <= self.row <= 8:
                    return 12
            if self.column in ("I", "J"):
                if 3 <= self.row <= 4:
                    return 13
                if 5 <= self.row <= 6:
                    return 14
                if 7 <= self.row <= 8:
                    return 15

        raise ValueError(f"Invalid zone x={self.x},y={self.y}")

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
    platform: constants.Platform = Field()
    level: int
    team_id: constants.Factions = Field(validation_alias="team")
    # TODO: make this an Enum
    squad: str = Field(validation_alias="platoon")
    # TODO: make this an Enum
    loadout: str
    score: PlayerScore = Field(validation_alias="scoreData")
    position: Position = Field(validation_alias="worldPosition")

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str):
        return constants.Platform(v.lower())


class PlayersResponse(BaseModel):
    players: dict[str, Player]
