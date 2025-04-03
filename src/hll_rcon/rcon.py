from hll_rcon.connection import HLLConnection
from hll_rcon.types.server_requests import ContentBody
from hll_rcon.types.server_responses import (
    RconResponse,
    RconCommandResponse,
    ClientReferenceDataResponse,
)
import orjson
from hll_rcon.types.constants import Platform, RconCommands, ServerInformationCommands
import hll_rcon.types.server_responses as responses
import json
from loguru import logger
from hll_rcon.types import maps


class BaseRcon:
    """Implements the RCON V2 protocol"""

    def __init__(self, host: str, port: int, password: str) -> None:
        self.connection = HLLConnection()
        self.connection.connect(host, port, password)

    def get_all_commands(self) -> dict[str, RconCommandResponse]:
        """Discover all queryable RCON commands from the server"""
        response = self.connection.request(RconCommands.DISPLAYABLE_COMMANDS, None)
        body = orjson.loads(response.body)
        return {
            cmd["iD"]: RconCommandResponse.model_validate(cmd)
            for cmd in body["entries"]
        }

    def discover_new_commands(self) -> set[str]:
        """Compare the game server commands to RconCommands"""
        commands = self.get_all_commands()
        new_commands: set[str] = set(cmd for cmd in commands if cmd not in RconCommands)
        return new_commands

    def get_client_reference_data(self, command_id: str) -> ClientReferenceDataResponse:
        response = self.connection.request(
            RconCommands.CLIENT_REFERENCE_DATA, command_id
        ).body

        return ClientReferenceDataResponse.model_validate_json(response)

    # Console Admin Commands

    def add_admin(self):
        raise NotImplementedError

    def remove_admin(self):
        raise NotImplementedError

    # Map Rotation Commands

    def get_available_maps(self) -> list[maps.Layer]:
        # Any of the commands dealing with the rotation when queried will
        # respond with the available maps
        response = self.get_client_reference_data(RconCommands.ADD_MAP_TO_ROTATION)
        raw_maps: list[str] = []
        for param in response.parameters:
            if param.id == "MapName":
                raw_maps: list[str] = param.as_list()

        # This intentionally fails and bubbles up a KeyError if we are missing a map
        # so we know we have an issue and can add the new map
        return [maps.LAYERS[map_id.lower()] for map_id in raw_maps]

    def add_map_to_rotation(self):
        raise NotImplementedError

    def remove_map_from_rotation(self):
        raise NotImplementedError

    # Map Sequence Commands

    def add_map_to_sequence(self):
        raise NotImplementedError

    def shuffle_map_sequence(self):
        raise NotImplementedError

    def move_map_in_sequence(self):
        raise NotImplementedError

    def remove_map_from_sequence(self):
        raise NotImplementedError

    # Map Commands

    def change_sector_layout(self):
        raise NotImplementedError

    def change_current_map(self):
        raise NotImplementedError

    # Player Commands

    def kick_player(self, player_id: str):
        raise NotImplementedError

    def message_player(self, player_id: str, message: str):
        raise NotImplementedError

    def perma_ban(self):
        raise NotImplementedError

    def punish_player(self):
        raise NotImplementedError

    def remove_perma_ban(self):
        raise NotImplementedError

    def remove_temp_ban(self):
        raise NotImplementedError

    def temp_ban(self):
        raise NotImplementedError

    # Basic Settings Commands

    def set_auto_balance(self, enabled: bool = True):
        raise NotImplementedError

    def set_auto_balance_threshold(self, threshold: int):
        raise NotImplementedError

    def set_high_ping_threshold(self, threshold: int):
        raise NotImplementedError

    def reset_kick_threshold(self):
        raise NotImplementedError

    def set_broadcast(self):
        raise NotImplementedError

    def set_vote_kick_enabled(self):
        raise NotImplementedError

    def set_vote_kick_threshold(self):
        raise NotImplementedError

    def set_welcome_message(self):
        # sendserverinformation
        raise NotImplementedError

    def set_idle_kick_duration(self):
        raise NotImplementedError

    def set_max_queued_players(self):
        raise NotImplementedError

    def set_team_switch_cooldown(self):
        raise NotImplementedError

        # Miscellaneous Commands

    def get_logs(self):
        raise NotImplementedError

    def client_reference_data(self):
        raise NotImplementedError

    def server_information(
        self, command: ServerInformationCommands, value: str | None = None
    ) -> RconResponse:
        return self.connection.request(
            command=RconCommands.SERVER_INFORMATION,
            body=ContentBody(name=command, value=value),
        )

    # Intentionally Not Implemented Commands

    def login(self):
        raise NotImplementedError

    # Desired Commands
    # These do not exist but need to prior to it being production ready


class Rcon(BaseRcon):
    """Adds additional commands comprised of the base RCON commands"""

    # Server Meta Data Commands

    def get_server_config(self) -> responses.ServerConfig:
        response = self.server_information(ServerInformationCommands.SERVER_CONFIG)
        return responses.ServerConfig.model_validate_json(response.body)

    def get_session_info(self) -> responses.SessionInfo:
        response = self.server_information(ServerInformationCommands.SESSION)
        return responses.SessionInfo.model_validate_json(response.body)

    def get_server_name(self) -> str:
        return self.get_server_config().name

    def get_server_build_number(self) -> str:
        return self.get_server_config().build_number

    def get_server_build_revision(self) -> str:
        return self.get_server_config().revision

    def get_server_build(self) -> str:
        """Return the build_number:build_revision"""
        return f"{self.get_server_build_number()}:{self.get_server_build_revision()}"

    def get_supported_platforms(self) -> set[Platform]:
        return self.get_server_config().supported_platforms

    # Map Rotation Commands

    def get_map_rotation(self) -> responses.MapRotation:
        response = self.server_information(ServerInformationCommands.MAP_ROTATION)

        maps = [
            responses.Map.model_validate(rm)
            for rm in orjson.loads(response.body)["mAPS"]
        ]
        return responses.MapRotation(maps=maps)

    # Map Sequence Commands

    # Player Commands

    def get_player(self, player_id: str):
        response = self.server_information(
            ServerInformationCommands.PLAYER, value=player_id
        )
        return orjson.dumps(orjson.loads(response.body))

    def get_players(self):
        response = self.server_information(ServerInformationCommands.PLAYERS)

        # logger.info(f"{orjson.dumps(orjson.loads(response.body))}")

        raw_players = orjson.loads(response.body)["players"]
        parsed_players: dict[str, responses.Player] = {}
        for player in raw_players:
            # Adjust the raw player to match our pydantic model
            player["scoreData"]["kills"] = player["kills"]
            player["scoreData"]["deaths"] = player["deaths"]
            # TODO: do this a better way
            player["worldPosition"]["vertical_map"] = True
            del player["kills"]
            del player["deaths"]
            player = responses.Player.model_validate(player)
            parsed_players[player.player_id] = player

        return responses.PlayersResponse(players=parsed_players)
