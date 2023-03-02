import inspect
import os
from contextlib import asynccontextmanager
from itertools import cycle
from typing import AsyncGenerator, Iterable, Self

import pydantic
import trio
from loguru import logger

TCP_TIMEOUT = 10


class HllConnection:
    """Represents an underlying low level socket connection to the game server and returns raw results"""

    def __init__(self, ip_addr: str, port: int, password: str) -> None:
        self.ip_addr = ip_addr
        self.port = int(port)
        self.password = password
        self._xor_key: bytes
        self._connection: trio.SocketStream | None = None
        self.logged_in = False

    @classmethod
    def _xor_encode(
        cls, message: str | bytes, xor_key: bytes, encoding: str = "utf-8"
    ) -> bytes:
        """XOR encrypt the given message with the given XOR key"""
        if isinstance(message, str):
            message = message.encode(encoding=encoding)

        return bytes(
            [
                message_char ^ xor_char
                for message_char, xor_char in zip(message, cycle(xor_key))
            ]
        )

    @classmethod
    def _xor_decode(cls, cipher_text: str | bytes, xor_key: bytes) -> str:
        """XOR decrypt the given cipher text with the given XOR key"""
        return cls._xor_encode(cipher_text, xor_key).decode("utf-8")

    @classmethod
    async def setup(cls, ip_addr: str, port: int, password: str) -> Self:
        """Create and return an instance after it has connected to the game server"""
        instance = HllConnection(ip_addr, port, password)
        await instance.connect()
        return instance

    @property
    def xor_key(self):
        return self._xor_key

    @property
    def connection(self) -> trio.SocketStream:
        if self._connection is not None:
            return self._connection
        else:
            raise ValueError("Invalid Connection")

    async def _connect(self):
        with trio.move_on_after(TCP_TIMEOUT):
            logger.debug(f"{id(self)} Opening socket")
            self._connection = await trio.open_tcp_stream(self.ip_addr, self.port)
            logger.debug(f"{id(self)} Socket open")

    async def connect(self):
        while self._connection is None:
            # TODO: This is probably dumb and connection raises a ValueError if it
            # isn't connected, should probably catch that and try up to a user
            # configurable number of retries or timeout or both to re-connect this socket
            # before failing
            await self._connect()

        # The very first thing the game server will return is the XOR key that all
        # subsequent requests require
        with trio.move_on_after(TCP_TIMEOUT):
            logger.debug(f"{id(self)} Getting XOR key in {id(self)}")
            self._xor_key = await self.connection.receive_some()
            logger.debug(f"{id(self)} Got XOR key={self.xor_key} in {id(self)}")

        with trio.move_on_after(TCP_TIMEOUT):
            logger.debug(f"{id(self)} Logging in")
            await self.login()
            # logger.debug(self.connection)
            logger.debug(f"{id(self)} Logged in")

    async def _send(self, content: str):
        """XOR the content and sendd to the game server, returning the game server response"""
        logger.debug(f"{id(self)} Sending {content=} to the game server")
        xored_content = HllConnection._xor_encode(content, self.xor_key)
        with trio.move_on_after(TCP_TIMEOUT):
            await self.connection.send_all(xored_content)
            result = await self.connection.receive_some()
            return HllConnection._xor_decode(result, self.xor_key)

    async def login(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Login {self.password}"
        return await self._send(content)

    async def get_server_name(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Name"
        return await self._send(content)

    async def get_current_max_player_slots(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Slots"
        return await self._send(content)

    async def get_gamestate(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get GameState"
        return await self._send(content)

    async def get_max_queue_size(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get MaxQueuedPlayers"
        return await self._send(content)

    async def set_max_queue_size(self, size: int):
        raise NotImplementedError

    async def get_num_vip_slots(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get NumVipSlots"
        return await self._send(content)

    async def set_num_vip_slots(self, amount: int):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({amount=})"  # type: ignore
        )
        content = f"SetNumVipSlots {amount}"
        return await self._send(content)

    async def set_welcome_message(self, message: str):
        raise NotImplementedError

    async def set_broadcast_message(self, message: str | None):
        raise NotImplementedError

    async def reset_broadcast_message(self):
        raise NotImplementedError

    async def get_game_logs(self, minutes: int, filter: str):
        raise NotImplementedError

    async def get_current_map(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Map"
        return await self._send(content)

    async def get_available_maps(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get MapsForRotation"
        return await self._send(content)

    async def get_map_rotation(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"RotList"
        return await self._send(content)

    async def add_map_to_rotation(
        self,
        name: str,
        after_map_name: str | None,
        after_map_ordinal: int | None = 1,
    ):
        raise NotImplementedError

    async def remove_map_from_rotation(self, name: str, ordinal: int | None = 1):
        raise NotImplementedError

    async def set_current_map(self, name: str, ordinal: int | None = 1):
        raise NotImplementedError

    async def get_players(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Players"
        return await self._send(content)

    async def get_player_steam_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get PlayerIds"
        return await self._send(content)

    async def get_admin_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AdminIds"
        return await self._send(content)

    async def get_admin_groups(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AdminGroups"
        return await self._send(content)

    async def get_vip_ids(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VipIds"
        return await self._send(content)

    async def get_player_info(self, player_name: str):
        raise NotImplementedError

    async def add_admin(self, steam_id_64: str, role: str, name: str | None):
        raise NotImplementedError

    async def remove_admin(self, steam_id_64: str):
        raise NotImplementedError

    async def add_vip(self, steam_id_64: str, name: str | None):
        raise NotImplementedError

    async def remove_vip(self, steam_id_64: str):
        raise NotImplementedError

    async def get_temp_bans(self):
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get TempBans"
        return await self._send(content)

    async def get_permanent_bans(self):
        raise NotImplementedError

    async def message_player(
        self, steam_id_64: str | None, player_name: str | None, message: str
    ):
        raise NotImplementedError

    async def punish_player(self, player_name: str, reason: str | None):
        raise NotImplementedError

    async def switch_player_on_death(self, player_name: str):
        raise NotImplementedError

    async def switch_player_now(self, player_name: str):
        raise NotImplementedError

    async def kick_player(self, player_name: str, reason: str | None):
        raise NotImplementedError

    async def temp_ban_player(
        self,
        steam_id_64: str | None,
        player_name: str | None,
        duration: int | None,
        reason: str | None,
        by_admin_name: str | None,
    ):
        raise NotImplementedError

    async def perma_ban_player(
        self,
        steam_id_64: str | None,
        player_name: str | None,
        duration: int | None,
        reason: str | None,
        by_admin_name: str | None,
    ):
        raise NotImplementedError

    async def remove_temp_ban(self, ban_log: str):
        raise NotImplementedError

    async def remove_perma_ban(self, ban_log: str):
        raise NotImplementedError

    async def get_idle_kick_time(self):
        raise NotImplementedError

    async def set_idle_kick_time(self, threshold_minutes: int):
        raise NotImplementedError

    async def get_high_ping_limit(self):
        raise NotImplementedError

    async def set_high_ping_limit(self, threshold: int):
        raise NotImplementedError

    async def get_team_switch_cooldown(self):
        raise NotImplementedError

    async def set_team_switch_cooldown(self, cooldown: int):
        raise NotImplementedError

    async def get_auto_balance_enabled(self):
        raise NotImplementedError

    async def enable_auto_balance(self):
        raise NotImplementedError

    async def disable_auto_balance(self):
        raise NotImplementedError

    async def get_auto_balance_threshold(self):
        raise NotImplementedError

    async def set_auto_balance_threshold(self, threshold: int):
        raise NotImplementedError

    async def get_vote_kick_enabled(self):
        raise NotImplementedError

    async def enable_vote_kick(self):
        raise NotImplementedError

    async def disable_vote_kick(self):
        raise NotImplementedError

    async def get_vote_kick_threshold(self):
        raise NotImplementedError

    async def set_vote_kick_threshold(self, thresholds: Iterable[tuple[int, int]]):
        raise NotImplementedError

    async def reset_vote_kick_threshold(self):
        raise NotImplementedError

    async def get_censored_words(self):
        raise NotImplementedError

    async def censor_words(self, words: str):
        raise NotImplementedError

    async def uncensor_words(self, words: str):
        raise NotImplementedError


class AsyncRcon:
    """Represents a high level RCON connection to the game server and returns processed results"""

    def __init__(
        self, ip_addr: str, port: str, password: str, connection_pool_size: int = 4
    ) -> None:
        self._ip_addr = ip_addr
        self._port = int(port)
        self._password = password
        self.connections: list[HllConnection] = []
        if connection_pool_size < 1:
            raise ValueError(f"connection_pool_size must be a positive integer")

        self.connection_pool_size = connection_pool_size
        self.connection_limit = trio.CapacityLimiter(connection_pool_size)

    async def setup(self):
        """Create `connection_pool_size` HllConnection instances"""

        async def _inner_setup():
            connection = await HllConnection.setup(
                self._ip_addr, self._port, self._password
            )
            logger.debug(
                f"Connection {_+1}/{self.connection_pool_size} {id(self)} opened"
            )
            self.connections.append(connection)

        async with trio.open_nursery() as nursery:
            for _ in range(self.connection_pool_size):
                logger.debug(f"Opening connection {_+1}/{self.connection_pool_size}")
                nursery.start_soon(_inner_setup)

    @asynccontextmanager
    async def _get_connection(self) -> AsyncGenerator[HllConnection, None]:
        async with self.connection_limit:
            # in theory we never need to check for a connection being unavailable
            # because trio.CapacityLimiter should handle this for us and block if
            # it needs to wait for another connection
            connection = self.connections.pop()
            yield connection
            self.connections.append(connection)

    @staticmethod
    def to_list(raw_list: str) -> list[str]:
        """Convert a game server tab delimited result string to a list"""
        expected_length, *items = raw_list.split("\t")
        expected_length = int(expected_length)

        if raw_list.endswith("\t"):
            expected_length += 1

        if len(items) != expected_length:
            logger.debug(f"{expected_length=}")
            logger.debug(f"{len(items)=}")
            logger.debug(f"{items=}")
            raise ValueError("List does not match expected length")

        return items

    async def login(self):
        async with self._get_connection() as conn:
            result = await conn.login()
            logger.debug(f"{id(self)} login {result=}")

    async def get_server_name(self):
        async with self._get_connection() as conn:
            result = await conn.get_server_name()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_current_max_player_slots(self):
        async with self._get_connection() as conn:
            result = await conn.get_current_max_player_slots()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_gamestate(self):
        async with self._get_connection() as conn:
            result = await conn.get_gamestate()
            logger.debug(
                f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_max_queue_size(self):
        async with self._get_connection() as conn:
            result = await conn.get_max_queue_size()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def set_max_queue_size(self, size: int):
        raise NotImplementedError

    async def get_num_vip_slots(self):
        async with self._get_connection() as conn:
            result = await conn.get_num_vip_slots()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def set_num_vip_slots(self, amount: int):
        class Amount(pydantic.BaseModel):
            amount: pydantic.conint(ge=1)  # type: ignore

        try:
            args = Amount(amount=amount)
        except ValueError as e:
            logger.error(f"{amount=} must be a positive integer")
            raise e

        async with self._get_connection() as conn:
            result = await conn.set_num_vip_slots(args.amount)
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def set_welcome_message(self, message: str):
        raise NotImplementedError

    async def set_broadcast_message(self, message: str | None):
        raise NotImplementedError

    async def reset_broadcast_message(self):
        raise NotImplementedError

    async def get_game_logs(self, minutes: int, filter: str):
        raise NotImplementedError

    async def get_current_map(self):
        async with self._get_connection() as conn:
            result = await conn.get_current_map()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_available_maps(self):
        async with self._get_connection() as conn:
            result = await conn.get_available_maps()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_map_rotation(self):
        async with self._get_connection() as conn:
            result = await conn.get_map_rotation()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def add_map_to_rotation(
        self,
        name: str,
        after_map_name: str | None,
        after_map_ordinal: int | None = 1,
    ):
        raise NotImplementedError

    async def remove_map_from_rotation(self, name: str, ordinal: int | None = 1):
        raise NotImplementedError

    async def set_current_map(self, name: str, ordinal: int | None = 1):
        raise NotImplementedError

    async def get_players(self):
        async with self._get_connection() as conn:
            result = await conn.get_players()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_player_steam_ids(self):
        async with self._get_connection() as conn:
            result = await conn.get_player_steam_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_admin_ids(self):
        async with self._get_connection() as conn:
            result = await conn.get_admin_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_admin_groups(self):
        async with self._get_connection() as conn:
            result = await conn.get_admin_groups()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_vip_ids(self):
        async with self._get_connection() as conn:
            result = await conn.get_vip_ids()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )

    async def get_player_info(self, player_name: str):
        raise NotImplementedError

    async def add_admin(self, steam_id_64: str, role: str, name: str | None):
        raise NotImplementedError

    async def remove_admin(self, steam_id_64: str):
        raise NotImplementedError

    async def add_vip(self, steam_id_64: str, name: str | None):
        raise NotImplementedError

    async def remove_vip(self, steam_id_64: str):
        raise NotImplementedError

    async def get_temp_bans(self):
        async with self._get_connection() as conn:
            result = await conn.get_temp_bans()
            logger.debug(
                f"{id(conn)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function} {result=}"  # type: ignore
            )
            return AsyncRcon.to_list(result)

    async def get_permanent_bans(self):
        raise NotImplementedError

    async def message_player(
        self, steam_id_64: str | None, player_name: str | None, message: str
    ):
        raise NotImplementedError

    async def punish_player(self, player_name: str, reason: str | None):
        raise NotImplementedError

    async def switch_player_on_death(self, player_name: str):
        raise NotImplementedError

    async def switch_player_now(self, player_name: str):
        raise NotImplementedError

    async def kick_player(self, player_name: str, reason: str | None):
        raise NotImplementedError

    async def temp_ban_player(
        self,
        steam_id_64: str | None,
        player_name: str | None,
        duration: int | None,
        reason: str | None,
        by_admin_name: str | None,
    ):
        raise NotImplementedError

    async def perma_ban_player(
        self,
        steam_id_64: str | None,
        player_name: str | None,
        duration: int | None,
        reason: str | None,
        by_admin_name: str | None,
    ):
        raise NotImplementedError

    async def remove_temp_ban(self, ban_log: str):
        raise NotImplementedError

    async def remove_perma_ban(self, ban_log: str):
        raise NotImplementedError

    async def get_idle_kick_time(self):
        raise NotImplementedError

    async def set_idle_kick_time(self, threshold_minutes: int):
        raise NotImplementedError

    async def get_high_ping_limit(self):
        raise NotImplementedError

    async def set_high_ping_limit(self, threshold: int):
        raise NotImplementedError

    async def get_team_switch_cooldown(self):
        raise NotImplementedError

    async def set_team_switch_cooldown(self, cooldown: int):
        raise NotImplementedError

    async def get_auto_balance_enabled(self):
        raise NotImplementedError

    async def enable_auto_balance(self):
        raise NotImplementedError

    async def disable_auto_balance(self):
        raise NotImplementedError

    async def get_auto_balance_threshold(self):
        raise NotImplementedError

    async def set_auto_balance_threshold(self, threshold: int):
        raise NotImplementedError

    async def get_vote_kick_enabled(self):
        raise NotImplementedError

    async def enable_vote_kick(self):
        raise NotImplementedError

    async def disable_vote_kick(self):
        raise NotImplementedError

    async def get_vote_kick_threshold(self):
        raise NotImplementedError

    async def set_vote_kick_threshold(self, thresholds: Iterable[tuple[int, int]]):
        raise NotImplementedError

    async def reset_vote_kick_threshold(self):
        raise NotImplementedError

    async def get_censored_words(self):
        raise NotImplementedError

    async def censor_words(self, words: str):
        raise NotImplementedError

    async def uncensor_words(self, words: str):
        raise NotImplementedError


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

    if not host or not port or not password:
        logger.error(f"RCON_HOST, RCON_PORT or RCON_PASSWORD not set")
        return

    rcon = AsyncRcon(host, port, password)
    await rcon.setup()
    async with trio.open_nursery() as nursery:
        pass
        # nursery.start_soon(rcon.get_num_vip_slots)
        # nursery.start_soon(rcon.get_max_queue_size)
        # nursery.start_soon(rcon.get_server_name)
        # nursery.start_soon(rcon.get_current_max_player_slots)
        # nursery.start_soon(rcon.get_gamestate)
        # nursery.start_soon(rcon.get_current_map)
        # nursery.start_soon(rcon.get_available_maps)
        # nursery.start_soon(rcon.get_map_rotation)
        # nursery.start_soon(rcon.get_players)
        # nursery.start_soon(rcon.get_player_steam_ids)
        # nursery.start_soon(rcon.get_admin_ids)
        # nursery.start_soon(rcon.get_admin_groups)
        # nursery.start_soon(rcon.get_temp_bans)

    logger.debug(f"===========================")
    bans = await rcon.get_temp_bans()
    for b in bans:
        if b:
            print(b)

    logger.debug(f"===========================")
    # await rcon.get_num_vip_slots()
    # await rcon.set_num_vip_slots()
    # await rcon.get_num_vip_slots()

    # await rcon.get_max_queue_size()

    # await rcon.connect()


if __name__ == "__main__":
    # trio.run(main, instruments=[Tracer()])
    trio.run(main)
