import os
from itertools import cycle
from typing import Iterable

import trio
from loguru import logger


class HllConnection:
    def __init__(self) -> None:
        pass


class AsyncRcon:
    """"""

    def __init__(self, ip_addr: str, port: str, password: str) -> None:
        self.ip_addr = ip_addr
        self.port = int(port)
        self.password = password
        self.xor_key: bytes

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

    async def connect(self):
        logger.info(f"Connecting to {self.ip_addr}:{self.port} {self.password=}")
        self.connection = await trio.open_tcp_stream(self.ip_addr, self.port)
        xor_key = await self.connection.receive_some()
        print(f"{xor_key=}")
        print(f"{bytes.decode(xor_key)=}")
        # async with self.connection:
        #     async for data in self.connection:
        #         print(f"got: {data!r}")
        #     print(f"connection closed")

        print(self.connection)

    async def login(self):
        raise NotImplementedError

    async def get_name(self):
        raise NotImplementedError

    async def get_slots(self):
        raise NotImplementedError

    async def get_gamestate(self):
        raise NotImplementedError

    async def get_max_queued_players(self):
        raise NotImplementedError

    async def set_max_queued_players(self, size: int):
        raise NotImplementedError

    async def get_num_vip_slots(self):
        raise NotImplementedError

    async def set_num_vip_slots(self, amount: int):
        raise NotImplementedError

    async def set_welcome_message(self, message: str):
        raise NotImplementedError

    async def broadcast(self, message: str | None):
        raise NotImplementedError

    async def get_game_logs(self, minutes: int, filter: str):
        raise NotImplementedError

    async def get_map(self):
        raise NotImplementedError

    async def get_available_maps(self):
        raise NotImplementedError

    async def get_map_rotation(self):
        raise NotImplementedError

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
        raise NotImplementedError

    async def get_player_steam_ids(self):
        raise NotImplementedError

    async def get_admin_ids(self):
        raise NotImplementedError

    async def get_admin_groups(self):
        raise NotImplementedError

    async def get_vip_ids(self):
        raise NotImplementedError

    async def get_player_info(self, player_name: str):
        raise NotImplementedError

    async def add_admin(self, steam_id_64: str, role: str, name: str | None):
        raise NotImplementedError

    async def remove_admin(self, steam_id_64: str):
        raise NotImplementedError

    async def dadd_vip(self, steam_id_64: str, name: str | None):
        raise NotImplementedError

    async def dremove_vip(self, steam_id_64: str):
        raise NotImplementedError

    async def get_temp_bans(self):
        raise NotImplementedError

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

    async def get_idle_time(self):
        raise NotImplementedError

    async def get_high_ping_limit(self):
        raise NotImplementedError

    async def get_team_switch_cooldown(self):
        raise NotImplementedError

    async def get_auto_balance_enabled(self):
        raise NotImplementedError

    async def get_auto_balance_threshold(self):
        raise NotImplementedError

    async def get_vote_kick_enabled(self):
        raise NotImplementedError

    async def get_vote_kick_threshold(self):
        raise NotImplementedError

    async def get_censored_words(self):
        raise NotImplementedError

    async def set_idle_kick_time(self, threshold_minutes: int):
        raise NotImplementedError

    async def set_high_ping_limit(self, threshold: int):
        raise NotImplementedError

    async def set_team_switch_cooldown(self, cooldown: int):
        raise NotImplementedError

    async def enable_auto_balance(self):
        raise NotImplementedError

    async def disable_auto_balance(self):
        raise NotImplementedError

    async def set_auto_balance_threshold(self, threshold: int):
        raise NotImplementedError

    async def enable_vote_kick(self):
        raise NotImplementedError

    async def disable_vote_kick(self):
        raise NotImplementedError

    async def set_vote_kick_threshold(self, thresholds: Iterable[tuple[int, int]]):
        raise NotImplementedError

    async def reset_vote_kick_threshold(self):
        raise NotImplementedError

    async def censor_words(self, words: str):
        raise NotImplementedError

    async def uncensor_words(self, words: str):
        raise NotImplementedError


async def main():
    host, port, password = (
        os.getenv("RCON_HOST"),
        os.getenv("RCON_PORT"),
        os.getenv("RCON_PASSWORD"),
    )
    rcon = AsyncRcon(host, port, password)
    # await rcon.connect()

    cipher_text = xor_encode("asdf", b"XOR")
    print(xor_decode(cipher_text, b"XOR"))


if __name__ == "__main__":
    trio.run(main)
