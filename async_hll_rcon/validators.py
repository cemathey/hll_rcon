from loguru import logger

from async_hll_rcon import constants
from async_hll_rcon.typedefs import FailedGameServerCommand, FailedGameServerResponse


def _validator_player_info(
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
        logger.error(f"{FailedGameServerResponse} for `{player_name=}`")
        raise FailedGameServerResponse

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
