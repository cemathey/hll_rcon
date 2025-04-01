from enum import IntEnum, StrEnum
import pydantic

from hll_rcon.types.constants import RCON_PROTOCOL_VERSION, ServerInformationCommands


class ContentBody(pydantic.BaseModel):
    """Models the `ContentBody` field on a request to the game server

    Some commands such as `ServerInformation` require a JSON object payload
    to determine which specific command to run (i.e. query players,
    serverconfig (v1 gamestate), etc.)

    In all cases this object is serialized to a JSON string regardless of
    the specific command format
    """

    name: ServerInformationCommands = pydantic.Field(serialization_alias="Name")
    value: str | None = pydantic.Field(default=None, serialization_alias="Value")


class RconRequest(pydantic.BaseModel):
    """The format the game server expects for a RCON request"""

    auth: str | None = pydantic.Field(default=None, serialization_alias="AuthToken")
    version: int = pydantic.Field(
        default=RCON_PROTOCOL_VERSION, serialization_alias="Version"
    )
    command: str = pydantic.Field(serialization_alias="Name")
    body: ContentBody | str | None = pydantic.Field(serialization_alias="ContentBody")

    class Config:
        populate_by_name = True

    @pydantic.field_serializer("body")
    def serialize_body(self, body: ContentBody | str | None):
        """The server always expects a string for the content body"""
        if body is None:
            return ""
        elif isinstance(body, ContentBody):
            return body.model_dump_json()
        elif isinstance(body, str):
            return body
        else:
            raise ValueError(f"Invalid body type: {type(body)}")
