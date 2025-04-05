from hll_rcon.types.constants import AdminGroup
from typing import Any

def valid_player_id_or_throw(player_id: str) -> None:
    if not is_valid_player_id(player_id):
        raise ValueError(f"{player_id} is not a valid player ID")


def is_valid_player_id(player_id: str) -> bool:
    """Check for valid player ID formats"""
    return is_steam_id(player_id) or is_team_17_id(player_id)


def is_steam_id(player_id: str) -> bool:
    if len(player_id) == 17 and player_id.isdigit():
        return True
    return False


def is_team_17_id(player_id: str) -> bool:
    """Checks for valid length/content for Team 17 hashed player IDs

    These can be from the Windows store; Xbox, Playstation or Epic
    """
    return len(player_id) == 32 and player_id.isalnum()


def valid_admin_group_or_throw(group: str):
    AdminGroup[group.lower()]

# TODO: make a typeddict for this
def adjust_player_dict(player_dict: dict[str, Any]) -> None:
    player_dict["scoreData"]["kills"] = player_dict["kills"]
    player_dict["scoreData"]["deaths"] = player_dict["deaths"]
    # TODO: do this a better way
    player_dict["worldPosition"]["vertical_map"] = True
    del player_dict["kills"]
    del player_dict["deaths"]