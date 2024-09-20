import os
from pprint import pprint

import trio
from loguru import logger

from hll_rcon.log_types import (
    BanLog,
    BanLogBan,
    ChatLog,
    ConnectLog,
    DisconnectLog,
    EnteredAdminCamLog,
    ExitedAdminCamLog,
    GameLogType,
    GameServerCredentials,
    KickLog,
    KillLog,
    LogTimeStamp,
    MatchEndLog,
    MatchStartLog,
    MessagedPlayerLog,
    TeamKillLog,
    TeamSwitchLog,
    VoteKickCompletedStatusLog,
    VoteKickExpiredLog,
    VoteKickPlayerVoteLog,
    VoteKickResultsLog,
    VoteKickStartedLog,
)
from hll_rcon.rcon import AsyncRcon
from hll_rcon.response_types import (
    AdminGroup,
    AdminId,
    AutoBalanceState,
    AutoBalanceThreshold,
    AvailableMaps,
    CensoredWord,
    GameState,
    HighPingLimit,
    IdleKickTime,
    InvalidTempBan,
    MapRotation,
    MaxQueueSize,
    NumVipSlots,
    PermanentBan,
    PlayerInfo,
    PlayerScore,
    ServerName,
    ServerPlayerSlots,
    Squad,
    TeamSwitchCoolDown,
    TemporaryBan,
    VipId,
    VoteKickState,
    VoteKickThreshold,
)
from hll_rcon.validators import IntegerGreaterOrEqualToOne


class Tracer(trio.abc.Instrument):
    def before_run(self):
        print("!!! run started")

    def _print_with_task(self, msg, task):
        # repr(task) is perhaps more useful than task.name in general,
        # but in context of a tutorial the extra noise is unhelpful.
        print(f"{msg}: {task.name}")

    def task_spawned(self, task):
        self._print_with_task("### new task spawned", task)

    def task_scheduled(self, task):
        self._print_with_task("### task scheduled", task)

    def before_task_step(self, task):
        self._print_with_task(">>> about to run one step of task", task)

    def after_task_step(self, task):
        self._print_with_task("<<< task step finished", task)

    def task_exited(self, task):
        self._print_with_task("### task exited", task)

    def before_io_wait(self, timeout):
        if timeout:
            print(f"### waiting for I/O for up to {timeout} seconds")
        else:
            print("### doing a quick check for I/O")
        self._sleep_time = trio.current_time()

    def after_io_wait(self, timeout):
        duration = trio.current_time() - self._sleep_time
        print(f"### finished I/O check (took {duration} seconds)")

    def after_run(self):
        print("!!! run finished")


async def main():
    host, port, password = (
        os.getenv("RCON_HOST"),
        os.getenv("RCON_PORT"),
        os.getenv("RCON_PASSWORD"),
    )

    logger.enable("hll_rcon")

    if not host or not port or not password:
        logger.error(f"RCON_HOST, RCON_PORT or RCON_PASSWORD not set")
        return

    rcon = AsyncRcon(host, port, password)
    await rcon.setup()
    # async with trio.open_nursery() as nursery:
    #     pass
    # nursery.start_soon(rcon.get_num_vip_slots)
    # nursery.start_soon(rcon.get_max_queue_size)
    # nursery.start_soon(rcon.get_server_name)
    # nursery.start_soon(rcon.get_current_max_player_slots)
    # nursery.start_soon(rcon.get_gamestate)
    # nursery.start_soon(rcon.get_current_map)
    # nursery.start_soon(rcon.get_available_maps)
    # nursery.start_soon(rcon.get_map_rotation)
    # nursery.start_soon(rcon.get_players)
    # nursery.start_soon(rcon.get_player_ids)
    # nursery.start_soon(rcon.get_admin_ids)
    # nursery.start_soon(rcon.get_admin_groups)
    # nursery.start_soon(rcon.get_temp_bans)

    logger.debug(f"===========================")
    # logger.debug(await rcon.get_admin_groups())
    # bans = await rcon.get_permanent_bans()
    # for b in bans:
    #     if b:
    #         print(b)

    # logger.debug(await rcon.get_game_logs(180))
    logger.debug(f"===========================")
    # logger.debug(await rcon.get_admin_groups())
    # logger.debug(await rcon.remove_vip("76561198004895814"))
    # logger.debug(await rcon.add_vip("76561198004895814", "NoodleArms"))
    # logger.debug(await rcon.set_broadcast_message("Test"))
    # logger.debug(await rcon.reset_broadcast_message())
    # logger.debug(await rcon.get_high_ping_limit())
    # logger.debug(await rcon.disable_high_ping_limit())
    # logger.debug(await rcon.get_high_ping_limit())
    # logger.debug(await rcon.set_high_ping_limit(0))
    # logger.debug(await rcon.enable_auto_balance())
    # logger.debug(await rcon.get_auto_balance_threshold())
    # logger.debug(await rcon.set_auto_balance_threshold(5))
    # logger.debug(await rcon.get_auto_balance_threshold())
    # logger.debug(await rcon.set_auto_balance_threshold(1))
    # logger.debug(await rcon.get_auto_balance_threshold())
    # logger.debug(await rcon.get_vote_kick_enabled())
    # logger.debug(await rcon.enable_vote_kick())
    # logger.debug(await rcon.get_vote_kick_enabled())
    # logger.debug(await rcon.disable_vote_kick())
    # logger.debug(await rcon.get_vote_kick_enabled())
    # logger.debug(await rcon.get_censored_words())
    # logger.debug(await rcon.censor_words(words=["bad", "words"]))
    # logger.debug(await rcon.get_censored_words())
    # logger.debug(await rcon.uncensor_words(words=["bad", "words"]))
    # logger.debug(await rcon.get_censored_words())
    # logger.debug(await rcon.get_vote_kick_thresholds())
    # logger.debug(await rcon.set_vote_kick_thresholds("-1,1"))
    # logger.debug(await rcon.get_vote_kick_thresholds())
    # logger.debug(await rcon.reset_vote_kick_threshold())
    # logger.debug(await rcon.get_vote_kick_thresholds())
    # logger.debug(await rcon.get_player_info("NoodleArms"))
    # logger.debug(await rcon.punish_player("NoodleArms", "Testing"))
    # logger.debug(await rcon.switch_player_on_death("NoodleArms"))
    # logger.debug(await rcon.kick_player("NoodleArms"))
    # logger.debug(await rcon.kick_player("NoodleArms", "Testing'"))
    # logger.debug(
    #     await rcon.temp_ban_player(
    #         steam_id_64="76561198004895814",
    #         player_name=None,
    #         duration=None,
    #         reason=None,
    #         by_admin_name=None,
    #     )
    # )
    # logger.debug(await rcon.remove_temp_ban(TempBanType(steam_id_64="76561198004895814", player_name=None, duration=None, reason=None, admin=None)))
    # bans = await rcon.get_permanent_bans()
    # for line in bans:
    #     print(line)

    # logger.debug(
    #     await rcon.remove_perma_ban(
    #         PermanentBanType(
    #             steam_id_64="76561198004895814",
    #             player_name=None,
    #             timestamp=datetime(
    #                 year=2023, month=3, day=6, hour=20, minute=59, second=29
    #             ),
    #             reason=None,
    #             admin=None,
    #         )
    #     )
    # )
    # logger.debug(await rcon.perma_ban_player("76561198004895814"))

    # bans = await rcon.get_permanent_bans()
    # for line in bans:
    #     print(line)
    # logger.debug(
    #     await rcon.remove_temp_ban(
    #         "76561198004895814 : banned for 2 hours on 2023.03.06-15.23.26"
    #     )
    # )

    # logger.debug(await rcon.get_temp_bans())
    # logger.debug(await rcon.set_idle_kick_time(1))
    # logger.debug(await rcon.get_idle_kick_time())
    # logger.debug(await rcon.set_idle_kick_time(0))
    # logger.debug(await rcon.get_idle_kick_time())

    # players = await rcon.get_player_ids()
    # pprint(players)

    # logger.info(f"{players=}")
    logs = await rcon.get_game_logs(360)
    logger.debug(await rcon.get_game_logs(5))

    for log in logs:
        if hasattr(log, "player_id"):
            logger.info(f"type={type(log)} player_id={log.player_id}")

    print(f"{len(logs)=}")
    none_Logs = [l for l in logs if not l]
    print(f"{len(none_Logs)=}")

    # ban_logs = [l for l in logs if isinstance(l, BanLog)]
    # for l in ban_logs:
    #     print(l)

    # logger.debug(await rcon.message_player("test message", "76561198004895814"))
    # logger.debug(
    #     await rcon.set_welcome_message(
    #         "Test welcome message\nnext line\n\ntwo lines down"
    #     )
    # )

    # for log in logs:
    #     print(type(log))

    # await rcon.get_num_vip_slots()

    # await rcon.set_num_vip_slots()
    # await rcon.get_num_vip_slots()

    # await rcon.get_max_queue_size()

    # await rcon.connect()


if __name__ == "__main__":
    # trio.run(main, instruments=[Tracer()])
    trio.run(main)
