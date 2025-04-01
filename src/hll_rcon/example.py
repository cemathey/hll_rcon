import json
import os
from pprint import pprint
from loguru import logger
from typing import Final

from hll_rcon.connection import HLLConnection
from hll_rcon.types.server_responses import SessionInfo
from hll_rcon.rcon import Rcon

if __name__ == "__main__":

    RCON_HOST: Final[str] = os.getenv("RCON_HOST", "")
    RCON_PORT: Final[int] = int(os.getenv("RCON_PORT", 0))
    RCON_PASSWORD: Final[str] = os.getenv("RCON_PASSWORD", "")

    # c = HLLConnection()
    # c.connect(RCON_HOST, RCON_PORT, RCON_PASSWORD)
    # resp = c.request(
    #     "ServerInformation", body=ContentBody(name=ServerInformationCommands.SESSION)
    # )
    # logger.info(f"Response={resp}")
    # logger.info(f"{json.dumps(resp.body)}")

    rcon = Rcon(RCON_HOST, RCON_PORT, RCON_PASSWORD)

    # c.connect(RCON_HOST, RCON_PORT, RCON_PASSWORD)

    # resp = c.request(
    #     "ServerInformation", body=ContentBody(name=ServerInformationCommands.PLAYERS)
    # )

    # resp = rcon.get_all_commands()
    # for c in resp:
    #     logger.info(c)

    # new_cmds = rcon.discover_new_commands()
    # logger.info(f"{new_cmds}")

    server_config = rcon.get_server_config()
    logger.info(f"{server_config=}")
    session = rcon.get_session_info()
    logger.info(f"{session=}")

    rotation = rcon.get_map_rotation()
    logger.info(f"{rotation=}")

    players = rcon.get_players()
    logger.info(f"{players=}")

    player = rcon.get_player("76561198004895814")
    logger.info(f"{player=}")
    # logger.info(f"{json.dumps(json.loads(server_config.body))}")

    # logger.info(f"Response={resp}")
    # logger.info("Body=")
    # pprint(body)
