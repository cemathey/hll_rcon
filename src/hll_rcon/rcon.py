from hll_rcon.connection import HLLConnection
from hll_rcon.types.server_requests import (
    AddAdminCommand,
    RemoveAdminCommand,
)
import orjson
from hll_rcon.types.constants import Platform, RconCommands, ServerInformationCommands
import hll_rcon.types.server_responses as responses
from hll_rcon.types import maps
from hll_rcon.utils import (
    valid_player_id_or_throw,
    valid_admin_group_or_throw,
    adjust_player_dict,
)
from typing import Callable
from hll_rcon.types import constants


def check_param(param_name: str, validator_func: Callable):
    def decorator(method):
        def wrapper(self, *args, **kwargs):
            if param_name in kwargs:
                value = kwargs[param_name]
            else:
                param_position = list(method.__code__.co_varnames).index(param_name) - 1
                if param_position < len(args):
                    value = args[param_position]
                else:
                    return method(self, *args, **kwargs)

                # Bubble up exceptions
                validator_func(value)

            return method(self, *args, **kwargs)

        return wrapper

    return decorator


class BaseRcon:
    """Implements the RCON V2 protocol"""

    def __init__(self, host: str, port: int, password: str) -> None:
        self.connection = HLLConnection()
        self.connection.connect(host, port, password)

    def get_all_commands(self) -> dict[str, responses.RconCommandResponse]:
        """Discover all queryable RCON commands from the server"""
        response = self.connection.request(RconCommands.DISPLAYABLE_COMMANDS, None)
        body = orjson.loads(response.body)
        return {
            cmd["iD"]: responses.RconCommandResponse.model_validate(cmd)
            for cmd in body["entries"]
        }

    def discover_new_commands(self) -> set[str]:
        """Compare the game server commands to RconCommands"""
        commands = self.get_all_commands()
        new_commands: set[str] = set(cmd for cmd in commands if cmd not in RconCommands)
        return new_commands

    def get_client_reference_data(
        self, command_id: str
    ) -> responses.ClientReferenceDataResponse:
        response = self.connection.request(
            RconCommands.CLIENT_REFERENCE_DATA, command_id
        ).body

        return responses.ClientReferenceDataResponse.model_validate_json(response)

    # Console Admin Commands
    @check_param("player_id", valid_player_id_or_throw)
    @check_param("group", valid_admin_group_or_throw)
    def add_admin(self, *, player_id: str, group: constants.AdminGroup, comment: str):
        self.connection.request(
            RconCommands.ADD_ADMIN,
            body=AddAdminCommand(
                player_id=player_id, group=group, comment=comment
            ).model_dump(by_alias=True),
        )

    @check_param("player_id", valid_player_id_or_throw)
    def remove_admin(self, *, player_id: str):
        self.connection.request(
            RconCommands.REMOVE_ADMIN,
            body=RemoveAdminCommand(player_id=player_id).model_dump(by_alias=True),
        )

    def get_console_admins(self) -> list[str]:
        response = self.get_client_reference_data(RconCommands.REMOVE_ADMIN)
        player_ids: list[str] = []
        for param in response.parameters:
            if param.id == "PlayerId":
                player_ids = param.as_list()
        return player_ids

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
    ) -> responses.RconResponse:
        return self.connection.request(
            command=RconCommands.SERVER_INFORMATION,
            body={"Name": command, "Value": value},
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
    def get_player(self, player_id: str) -> responses.Player:
        response = self.server_information(
            ServerInformationCommands.PLAYER, value=player_id
        )
        raw_player = orjson.loads(response.body)
        adjust_player_dict(raw_player)
        return responses.Player.model_validate(raw_player)

    def get_players(self) -> responses.PlayersResponse:
        response: responses.RconResponse = self.server_information(
            ServerInformationCommands.PLAYERS
        )

        raw_players = orjson.loads(response.body)["players"]
        parsed_players: dict[str, responses.Player] = {}
        for player in raw_players:
            # Adjust the raw player to match our pydantic model
            adjust_player_dict(player)
            player = responses.Player.model_validate(player)
            parsed_players[player.player_id] = player

        return responses.PlayersResponse(players=parsed_players)
