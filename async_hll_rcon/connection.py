import inspect
from itertools import cycle
from typing import Callable, Self

import trio
from loguru import logger
import pydantic

from async_hll_rcon import constants, exceptions
from async_hll_rcon.validators import (
    _gamestate_validator,
    _on_off_validator,
    _player_info_validator,
    _success_fail_validator,
)


class HllConnection:
    """Represents an underlying low level socket connection to the game server and returns raw results

    Performs minmal to no validation/error checking because all of that is done in AsyncRcon

    """

    def __init__(
        self,
        ip_addr: pydantic.IPvAnyAddress,
        port: int,
        password: str,
        receive_timeout: int = constants.TCP_TIMEOUT_READ,
        tcp_timeout: int = constants.TCP_TIMEOUT,
        max_buffer_size: int | None = constants.CHUNK_SIZE,
    ) -> None:
        self.ip_addr = ip_addr
        self.port = int(port)
        self.password = password
        self.receive_timeout = receive_timeout
        self.tcp_timeout = tcp_timeout
        self.max_buffer_size = max_buffer_size
        self.xor_key: bytes
        self._connection: trio.SocketStream | None = None
        self.logged_in = False

    @staticmethod
    def _validate_timeout(value: float) -> float:
        """Check that value is float like and positive for TCP timeouts"""
        try:
            float(value)
        except ValueError:
            raise ValueError(
                f"`timeout={value}` must be a float or castable to a float"
            )

        value = float(value)
        if value < 0:
            raise ValueError(f"`timeout={value}` must be >= 0")

        return value

    @staticmethod
    def _validate_max_buffer_size(value: int | None) -> int | None:
        """Check that value is int like and positive for socket receive buffer sizes"""
        if value is None:
            return value

        try:
            int(value)
        except ValueError:
            raise ValueError(
                f"`max_buffer_size={value}` must be an int, castable to int or None"
            )

        value = int(value)
        if value < 0:
            raise ValueError(f"`max_buffer_size={value}` must be >= 0 or None")

        return value

    @property
    def receive_timeout(self) -> float:
        return self._receive_timeout

    @receive_timeout.setter
    def receive_timeout(self, value: float) -> None:
        self._validate_timeout(value)

        self._receive_timeout = float(value)

    @property
    def tcp_timeout(self) -> float:
        return self._tcp_timeout

    @tcp_timeout.setter
    def tcp_timeout(self, value: float) -> None:
        self._validate_timeout(value)

        self._tcp_timeout = float(value)

    @property
    def max_buffer_size(self) -> int | None:
        return self._max_buffer_size

    @max_buffer_size.setter
    def max_buffer_size(self, value: int | None) -> None:
        self._max_buffer_size = self._validate_max_buffer_size(value)

    @property
    def connection(self) -> trio.SocketStream:
        """Safety check to make sure an unconnected instance isn't used"""
        if self._connection is not None:
            return self._connection
        else:
            raise ValueError("Socket connection to the game server not established.")

    @staticmethod
    def _xor_encode(
        message: str | bytes, xor_key: bytes, encoding: str = "utf-8"
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

    @staticmethod
    def _xor_decode(cipher_text: str | bytes, xor_key: bytes) -> str:
        """XOR decrypt the given cipher text with the given XOR key"""
        return HllConnection._xor_encode(cipher_text, xor_key).decode("utf-8")

    @classmethod
    async def setup(
        cls,
        ip_addr: pydantic.IPvAnyAddress,
        port: int,
        password: str,
        receive_timeout: int,
        tcp_timeout: int,
    ) -> Self:
        """Create and return an instance after it has connected to the game server"""
        instance = HllConnection(ip_addr, port, password, receive_timeout, tcp_timeout)
        await instance.connect()
        return instance

    async def _connect(self) -> None:
        """Open a socket to the game server and retrieve the XOR key"""
        with trio.fail_after(self.tcp_timeout):
            # We must cast the pydantic.IPv4AnyAddress to a string here or it fails
            self._connection = await trio.open_tcp_stream(str(self.ip_addr), self.port)

        # The very first thing the game server will return is the XOR key that all
        # subsequent requests require for encoding/decoding
        with trio.fail_after(self.tcp_timeout):
            self.xor_key = await self._receive_from_game_server()

    async def connect(self) -> None:
        """Connect to and log into the game server"""
        await self._connect()
        await self.login()

    async def _receive_from_game_server(
        self,
        validator: Callable | None = None,
        **kwargs,
    ) -> bytes:
        """Accumulate chunks of bytes from the game server and return them

        The game server does not indicate end of blocks of data in any way and does not
        send the empty (b"") value trio would need to iterate over the connection. Instead
        we repeatedly try to read from the socket until we time out at self.receive_timeout
        seconds and then return all the accumulated data
        """

        buffer = bytearray()
        while True:
            try:
                with trio.fail_after(self.receive_timeout):
                    buffer += await self.connection.receive_some(
                        max_bytes=self.max_buffer_size
                    )

                    # The game server does not send back any sort of EOF marker
                    # so there is no way to know when we're actually done, some
                    # return values can be identified as complete and valid return
                    # results, and if so we can return early, otherwise we block
                    # until we time out
                    logger.debug(f"{validator=}")
                    if validator and validator(
                        self._xor_decode(buffer, self.xor_key), **kwargs
                    ):
                        logger.debug(f"breaking on complete chunk")
                        break

            except trio.TooSlowError:
                if validator:
                    logger.error(
                        f"Timed out in {id(self)} buffer=`{self._xor_decode(buffer, self.xor_key)}`"
                    )
                    raise
                break

        return bytes(buffer)

    async def _send_to_game_server(
        self,
        content: str,
        response_validator: Callable | None = None,
        retry_attempts: int = 2,
        **kwargs,
    ) -> str:
        """XOR the content and send to the game server, returning the game server response"""
        logger.debug(f"{id(self)} {len(content)=} {content=}")
        xored_content = HllConnection._xor_encode(content, self.xor_key)
        result = None
        for _ in range(retry_attempts):
            try:
                with trio.fail_after(self.tcp_timeout):
                    logger.debug(f"sending content=`{content}`")
                    await self.connection.send_all(xored_content)
                    result = await self._receive_from_game_server(
                        validator=response_validator, **kwargs
                    )
                    break
            except (exceptions.FailedGameServerResponseError, trio.TooSlowError) as e:
                logger.error(
                    f"{id(self)} {content=} {len(content)=} Failed attempt #{_+1}/{retry_attempts} {e}"
                )
                continue

        if not result:
            raise exceptions.FailedGameServerCommandError

        logger.warning(f"received {len(result)=} bytes")

        return HllConnection._xor_decode(result, self.xor_key)

    async def login(self) -> str:
        """Log into the game server with the ip/port/password provided during initialization

        Returns:
            "SUCCESS" or "FAILURE"
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Login {self.password}"
        try:
            return await self._send_to_game_server(
                content, response_validator=_success_fail_validator
            )
        except exceptions.FailedGameServerCommandError:
            raise exceptions.AuthenticationError

    async def get_server_name(self) -> str:
        """Return the server name as defined in the game server `Server.ini` file"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Name"
        return await self._send_to_game_server(content)

    async def get_current_max_player_slots(self) -> str:
        """Return the number of players currently on the server and max players in the form X/Y"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Slots"
        return await self._send_to_game_server(content)

    async def get_gamestate(self) -> str:
        """Return the current round state

        Returns
            A string, including newlines in the format:

            Players: Allied: 46 - Axis: 46
            Score: Allied: 4 - Axis: 1
            Remaining Time: 0:25:23
            Map: carentan_offensive_ger
            Next Map: hurtgenforest_warfare_V2

        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get GameState"
        return await self._send_to_game_server(
            content, response_validator=_gamestate_validator
        )

    async def get_max_queue_size(self) -> str:
        """Return the maximum number of players allowed in the queue to join the server"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get MaxQueuedPlayers"
        return await self._send_to_game_server(content)

    async def set_max_queue_size(self, size: int) -> str:
        """Set the maximum number of players allowed in the queue to join the server (0 <= size <= 6)

        Returns
            "SUCCESS" or "FAILURE"
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetMaxQueuedPlayers {size}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_num_vip_slots(self) -> str:
        """Returns the number of reserved VIP slots"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get NumVipSlots"
        return await self._send_to_game_server(content)

    async def set_num_vip_slots(self, amount: int) -> str:
        """Set the number of reserved VIP slots on the server

        For example, setting this to 2 on a 100 slot server would only allow players
        with VIP access to join once 98 players are connected (regardless of those
        players VIP status)

        Returns
            "SUCCESS" or "FAILURE"
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({amount=})"  # type: ignore
        )
        content = f"SetNumVipSlots {amount}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def set_welcome_message(self, message: str) -> str:
        """Set the server welcome message

        Returns
            "SUCCESS" or "FAILURE"
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({message=})"  # type: ignore
        )
        content = f"Say {message}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def set_broadcast_message(self, message: str | None) -> str:
        """Set the current broadcast message, or clear it if message is None

        As of HLL v1.13.0.815373 resetting the broadcast message outside of the in game console is broken
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({message=})"  # type: ignore
        )
        if message:
            content = f"Broadcast {message}"
        else:
            raise NotImplementedError
            content = f"Broadcast  "

        logger.debug(f"{content=}")
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def clear_broadcast_message(self) -> str:
        """Clear the current broadcast message

        As of HLL v1.13.0.815373 resetting the broadcast message outside of the in game console is broken
        """
        raise NotImplementedError
        return await self.set_broadcast_message(None)

    async def get_game_logs(self, minutes: int, filter: str | None = None) -> str:
        """Return a new line delimited list of game logs

        Args
            minutes: The number of minutes worth of logs to return, it is not possible to retrieve
                logs after server restarts
            filter: Return only logs that contain this string in them

        Returns
            A string of log lines delimited by new lines, certain log types may contain new lines such as KICKs or MESSAGES
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({minutes=}, {filter=})"  # type: ignore
        )
        if filter is None:
            filter = ""

        content = f'ShowLog {minutes} "{filter}"'
        return await self._send_to_game_server(content)

    async def get_current_map(self) -> str:
        """Return the current map name"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Map"
        return await self._send_to_game_server(content)

    async def get_available_maps(self) -> str:
        """Return a HLL tab delimited list of all available map names."""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get MapsForRotation"
        return await self._send_to_game_server(content)

    async def get_map_rotation(self) -> str:
        """Return a newline delimited string of the currently set map rotation names"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"RotList"
        return await self._send_to_game_server(content)

    async def add_map_to_rotation(
        self,
        name: str,
        after_map_name: str | None = None,
        after_map_ordinal: int | None = None,
    ) -> str:
        """Add the map to the rotation in the specified spot, appends to the end of the rotation by default

        Returns
            SUCCESS or game server error messages
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        # TODO: Fix if they ever remove the prefix nonsense
        name = "/Game/Maps/" + name
        if after_map_name:
            after_map_name = "/Game/Maps/" + after_map_name

        content = f"RotAdd {name} {after_map_name or ''} {after_map_ordinal or ''}"
        return await self._send_to_game_server(content)

    async def remove_map_from_rotation(self, name: str, ordinal: int | None = 1) -> str:
        """Remove the specified map instance from the rotation

        Returns
            SUCCESS or game server error messages
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )

        # TODO: Fix if they ever remove the prefix nonsense
        name = "/Game/Maps/" + name

        content = f"RotDel {name} {ordinal or ''}"
        return await self._send_to_game_server(content)

    async def set_current_map(self, name: str, ordinal: int | None = 1) -> str:
        """Immediately change the game server to the map after a 60 second delay, the map must be in the rotation

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Map {name} {ordinal or ''}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_players(self) -> str:
        """Return a HLL tab delimited list of player names currently connected to the game server"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Players"
        return await self._send_to_game_server(content)

    async def get_player_steam_ids(self) -> str:
        """Return a HLL tab delimited list of player names and steam IDs in the format player_name : steam_id_64"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get PlayerIds"
        return await self._send_to_game_server(content)

    async def get_admin_ids(self) -> str:
        """Return a HLL tab delimited list of admins and their roles

        See also get_admin_groups()

        Returns
            tab delimited list in the form: steam_id_64 role "name"
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AdminIds"
        return await self._send_to_game_server(content)

    async def get_admin_groups(self) -> str:
        """Return a HLL tab delimited list of available admin roles"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AdminGroups"
        return await self._send_to_game_server(content)

    async def add_admin(
        self, steam_id_64: str, role: str, name: str | None = None
    ) -> str:
        """Grant the specified steam ID the specified role

        Role must be valid, see get_admin_groups()

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"AdminAdd {steam_id_64} {role} {name or ''}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def remove_admin(self, steam_id_64: str) -> str:
        """Remove all admin roles from the specified steam ID, see get_admin_groups() for possible admin roles

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"AdminDel {steam_id_64}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_vip_ids(self) -> str:
        """Return a HLL tab delimited list of VIP steam ID 64s and names"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VipIds"
        return await self._send_to_game_server(content)

    async def get_player_info(self, player_name: str) -> str:
        """Return detailed player info for the given player name

        Returns
            New line delimited string in the form:

            Name: Muller
            steamID64: 76561198148668981
            Team: Axis
            Role: HeavyMachineGunner
            Unit: 2 - CHARLIE
            Loadout: Standard Issue
            Kills: 39 - Deaths: 30
            Score: C 389, O 380, D 920, S 30
            Level: 77

        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}({player_name=})"  # type: ignore
        )
        content = f"PlayerInfo {player_name}"
        result = await self._send_to_game_server(
            content, _player_info_validator, player_name=player_name, conn_id=id(self)
        )

        logger.debug(f"{id(self)} {result=}")
        return result

    async def add_vip(self, steam_id_64: str, name: str | None) -> str:
        """Grant VIP status to the given steam ID

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"VipAdd {steam_id_64} {name}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def remove_vip(self, steam_id_64: str) -> str:
        """Remove VIP status from the given steam ID

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"VipDel {steam_id_64}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_temp_bans(self) -> str:
        """Return a HLL tab delimited list of temporary ban lists"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get TempBans"
        return await self._send_to_game_server(content)

    async def get_permanent_bans(self) -> str:
        """Return a HLL tab delimited list of permanent ban lists"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get PermaBans"
        return await self._send_to_game_server(content)

    async def message_player(
        self,
        message: str,
        steam_id_64: str | None = None,
        player_name: str | None = None,
    ) -> str:
        """Send an in game message to the specified player

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f'Message "{steam_id_64 or player_name}" "{message}"'
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def punish_player(self, player_name: str, reason: str | None = None) -> str:
        """Punish (kill in game) the specified player, will fail if they are not spawned

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Punish {player_name} {reason}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def switch_player_on_death(self, player_name: str) -> str:
        """Switch a player to the other team after their next death

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SwitchTeamOnDeath {player_name}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def switch_player_now(self, player_name: str) -> str:
        """Immediately switch a player to the other team

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SwitchTeamNow {player_name}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def kick_player(self, player_name: str, reason: str | None = None) -> str:
        """Remove a player from the server and show them the indicated reason

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Kick {player_name} {reason}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def temp_ban_player(
        self,
        steam_id_64: str | None = None,
        player_name: str | None = None,
        duration_hours: int | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
    ) -> str:
        """Ban a player from the server for the given number of hours and show them the indicated reason

        Args
            steam_id_64: optional if player name is provided
            player_name: optional if steam_id_64 is provided, will use steam_id_64 if both are passed
            duration_hours: number of hours to ban, will be cleared on game server restart, defaults to 2 if not provided
            reason: optional reason for the ban that is shown to the player
            by_admin_name: optional name for which admin or automated service banned the player
        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )

        if duration_hours is None:
            validated_duration = ""
        else:
            validated_duration = str(duration_hours)

        if reason is None:
            reason = ""

        if by_admin_name is None:
            by_admin_name = ""

        content = f'TempBan "{steam_id_64 or player_name}" {validated_duration} "{reason}" "{by_admin_name}"'
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def perma_ban_player(
        self,
        steam_id_64: str | None = None,
        player_name: str | None = None,
        reason: str | None = None,
        by_admin_name: str | None = None,
    ) -> str:
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        """Permanently ban a player and show them the indicated reason

        Args
            steam_id_64: optional if player name is provided
            player_name: optional if steam_id_64 is provided, will use steam_id_64 if both are passed
            reason: optional reason for the ban that is shown to the player
            by_admin_name: optional name for which admin or automated service banned the player

        Returns
            SUCCESS or FAIL
        """

        if reason is None:
            reason = ""

        if by_admin_name is None:
            by_admin_name = ""

        content = (
            f'PermaBan "{steam_id_64 or player_name}" "{reason}" "{by_admin_name}"'
        )
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def remove_temp_ban(self, ban_log: str) -> str:
        """Remove a temporary ban from a player

        Args
            ban_log: Must match the HLL ban log format returned from get_temp_bans

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"PardonTempBan {ban_log}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def remove_perma_ban(self, ban_log: str) -> str:
        """Remove a permanent ban from a player

        Args
            ban_log: Must match the HLL ban log format returned from get_permanent_bans()

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"PardonPermaBan {ban_log}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_idle_kick_time(self) -> str:
        """Return the current idle kick time in minutes"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Idletime"
        return await self._send_to_game_server(content)

    async def set_idle_kick_time(self, threshold_minutes: int) -> str:
        """Set the idle kick time in minutes

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetKickIdleTime {threshold_minutes}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_high_ping_limit(self) -> str:
        """Return the high ping limit in milliseconds"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get HighPing"
        return await self._send_to_game_server(content)

    async def set_high_ping_limit(self, threshold: int) -> str:
        """Set the high ping limit (player is kicked when they exceed) in milliseconds

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetHighPing {threshold}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def disable_high_ping_limit(self) -> str:
        """Disable (set to 0) the high ping limit

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        return await self.set_high_ping_limit(0)

    async def get_team_switch_cooldown(self) -> str:
        """Return the current team switch cool down in minutes"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get TeamSwitchCooldown"
        return await self._send_to_game_server(content)

    async def set_team_switch_cooldown(self, cooldown: int) -> str:
        """Set the team switch cool down in minutes

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetTeamSwitchCooldown {cooldown}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_auto_balance_enabled(self) -> str:
        """Return if team auto balance (enforced differences in team sizes) is enabled

        Returns
            'on' or 'off'
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AutoBalanceEnabled"
        return await self._send_to_game_server(
            content, response_validator=_on_off_validator
        )

    async def enable_auto_balance(self) -> str:
        """Enable the team auto balance (enforced differences in team sizes) feature

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutobalanceEnabled {constants.HLL_BOOL_ENABLED}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def disable_auto_balance(self) -> str:
        """Disable the team auto balance (enforced differences in team sizes) feature

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutobalanceEnabled {constants.HLL_BOOL_DISABLED}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_auto_balance_threshold(self) -> str:
        """Return the allowed team size difference before players are forced to join the other team"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get AutoBalanceThreshold"
        return await self._send_to_game_server(content)

    async def set_auto_balance_threshold(self, threshold: int) -> str:
        """Set the allowed team size difference before players are forced to join the other team

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetAutoBalanceThreshold {threshold}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_vote_kick_enabled(self) -> str:
        """Return if vote to kick players is enabled

        Returns
            'on' or 'off'
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VoteKickEnabled"
        return await self._send_to_game_server(
            content, response_validator=_on_off_validator
        )

    async def enable_vote_kick(self) -> str:
        """Enable the vote to kick players feature

        Returns
            SUCCESS or FAIL
        """

        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickEnabled  {constants.HLL_BOOL_ENABLED}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def disable_vote_kick(self) -> str:
        """Disable the vote to kick players feature

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickEnabled  {constants.HLL_BOOL_DISABLED}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_vote_kick_thresholds(self) -> str:
        """Return the required number of votes to remove from the server in threshold pairs

        Returns
            A comma separated list in the form: players, votes required for instance 0,1,10,5
                means when 10 players are on, 5 votes are required to remove a player
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get VoteKickThreshold"
        return await self._send_to_game_server(content)

    async def set_vote_kick_thresholds(self, threshold_pairs: str) -> str:
        """Set vote kick threshold pairs, the first entry must be for 0 players

        Args
            threshold_pairs: A comma separated list in the form: players, votes required for instance 0,1,10,5
                means when 10 players are on, 5 votes are required to remove a player
        Returns
            SUCCESS or FAIL or error message
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"SetVoteKickThreshold {threshold_pairs}"

        # This validator won't work 100% of the time since this can return error messages
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def clear_vote_kick_thresholds(self) -> str:
        """Clear vote kick threshold pairs

        Removes all the threshold pairs, the game server does not appear to have defaults

        Returns
            SUCCESS or FAIL
        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"ResetVoteKickThreshold"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def get_censored_words(self) -> str:
        """Return a HLL tab delimited list of all words that will be censored in game chat"""
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"Get Profanity"
        return await self._send_to_game_server(content)

    async def censor_words(self, words: str) -> str:
        """Append a comma delimited list of words to censor in game chat

        Args
            words: Must be a comma separated list, white space between commas is preserved
                and words are appended, adding a word that already exists will return SUCCESS
                but the word will not be duplicated

        Returns
            SUCCESS or FAIL

        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"BanProfanity {words}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )

    async def uncensor_words(self, words: str) -> str:
        """Remove a comma delimited list of words to censor in game chat

        Args
            words: Must be a comma separated list, response_validator=_success_fail_validator, white space between commas is preserved

        Returns
            SUCCESS or FAIL

        """
        logger.debug(
            f"{id(self)} {self.__class__.__name__}.{inspect.getframeinfo(inspect.currentframe()).function}()"  # type: ignore
        )
        content = f"UnbanProfanity {words}"
        return await self._send_to_game_server(
            content, response_validator=_success_fail_validator
        )
