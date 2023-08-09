from loguru import logger

from async_hll_rcon import constants
from async_hll_rcon.exceptions import (
    FailedGameServerResponseError,
)


def _success_fail_validator(result: str) -> bool:
    """Generic validator for commands that only return SUCCESS or FAIL"""
    if result == constants.SUCCESS_RESPONSE:
        return True
    elif result == constants.FAIL_RESPONSE:
        return False
    else:
        raise ValueError(
            f"{result=} not in ({constants.SUCCESS_RESPONSE}, {constants.FAIL_RESPONSE})"
        )


def _on_off_validator(result: str) -> bool:
    """Generic validator for commands that only return `on` or `off"""
    if result == constants.HLL_BOOL_ENABLED:
        return True
    elif result == constants.HLL_BOOL_DISABLED:
        return False
    else:
        raise ValueError(
            f"{result=} not in ({constants.HLL_BOOL_ENABLED}, {constants.HLL_BOOL_DISABLED})"
        )


def _player_info_validator(
    player_info: str, conn_id: int, player_name: str | None = None
) -> bool:
    """Return if the result from get_player_info appears to be complete"""
    logger.debug(f"{conn_id} _validator_player_info({player_info=}, {player_name=})")

    if player_info == constants.FAIL_RESPONSE:
        logger.warning(
            f"Received {player_info} in _validator_player_info for {player_name}"
        )
        return True

    if player_info == "":
        logger.error(f"{FailedGameServerResponseError} for `{player_name=}`")
        raise FailedGameServerResponseError

    is_complete = True

    required_keys = set(
        ["Name", "steamID64", "Team", "Role", "Kills", "Score", "Level"]
    )
    found_keys: set[str] = set()

    test_keys = player_info.split("\n")
    if len(test_keys) < len(required_keys):
        logger.debug(
            f"Bailing early because player info is too short: `{player_name=}` `{player_info=}`"
        )
        return False

    for test_key in test_keys:
        if test_key:
            key, _ = test_key.split(": ", maxsplit=1)
            found_keys.add(key)

    if not all(key in found_keys for key in required_keys):
        logger.error(f"{found_keys=} {required_keys=}")
        return False

    return is_complete


def _gamestate_validator(raw_gamestate: str) -> bool:
    """Return if the result from get_player_info appears to be complete"""
    logger.debug(f"_gamestate_validator({raw_gamestate=})")

    is_complete = True

    # Players: Allied: 46 - Axis: 46
    # Score: Allied: 4 - Axis: 1
    # Remaining Time: 0:25:23
    # Map: carentan_offensive_ger
    # Next Map: hurtgenforest_warfare_V2

    required_keys = set(["Players", "Score", "Remaining Time", "Map", "Next Map"])
    found_keys: set[str] = set()

    test_keys = raw_gamestate.split("\n")
    if len(test_keys) < len(required_keys):
        logger.debug(
            f"Bailing early because player info is too short: `{raw_gamestate=}`"
        )
        return False

    for test_key in test_keys:
        if test_key:
            key, _ = test_key.split(": ", maxsplit=1)
            found_keys.add(key)

    if not all(key in found_keys for key in required_keys):
        logger.error(f"{found_keys=} {required_keys=}")
        return False

    return is_complete
