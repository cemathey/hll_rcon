from enum import IntEnum, StrEnum
import pydantic

from typing import Any
from hll_rcon.types.constants import (
    RCON_PROTOCOL_VERSION,
    ServerInformationCommands,
    AdminGroup,
)
import orjson


class BaseCommand(pydantic.BaseModel):
    """Empty class to allow type checking through inheritance"""


class AddAdminCommand(BaseCommand):
    player_id: str = pydantic.Field(serialization_alias="PlayerId")
    group: AdminGroup
    comment: str


class RemoveAdminCommand(BaseCommand):
    player_id: str = pydantic.Field(serialization_alias="PlayerId")


class RconRequest(pydantic.BaseModel):
    """The format the game server expects for a RCON request"""

    auth: str | None = pydantic.Field(default=None, serialization_alias="AuthToken")
    version: int = pydantic.Field(
        default=RCON_PROTOCOL_VERSION, serialization_alias="Version"
    )
    command: str = pydantic.Field(serialization_alias="Name")
    body: dict[str, Any] | str | None = pydantic.Field(
        serialization_alias="ContentBody"
    )

    class Config:
        populate_by_name = True

    @pydantic.field_serializer("body")
    def serialize_body(self, body: dict[str, Any] | str | None) -> bytes | str:
        """The server always expects a string for the content body"""
        if body is None:
            return ""
        elif isinstance(body, dict):
            return orjson.dumps(body)
        elif isinstance(body, str):
            return body
        else:
            raise ValueError(f"Invalid body type: {type(body)}")
