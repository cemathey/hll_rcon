from datetime import datetime

import pytest

from async_hll_rcon.io import AsyncRcon, HllConnection
from async_hll_rcon.typedefs import BanType


@pytest.mark.parametrize("message, xor_key, expected", [("asdf", b"XOR", b"9<6>")])
def test_xor_encode(message, xor_key, expected):
    assert HllConnection._xor_encode(message, xor_key) == expected


@pytest.mark.parametrize("cipher_text, xor_key, expected", [(b"9<6>", b"XOR", "asdf")])
def test_xor_decode(cipher_text, xor_key, expected):
    assert HllConnection._xor_decode(cipher_text, xor_key) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "3\t\t\t",
            ["", "", ""],
        ),
        (
            '76561198154596433 : banned for 48 hours on 2023.03.02-00.00.08 for "Homophobic text chat" by admin "-Scab"\t76561198090370236 : banned for 2 hours on 2023.03.02-16.22.01 for "Being a dick is in fact against the server rules." by admin "NoodleArms"\t',
            [
                '76561198154596433 : banned for 48 hours on 2023.03.02-00.00.08 for "Homophobic text chat" by admin "-Scab"',
                '6561198090370236 : banned for 2 hours on 2023.03.02-16.22.01 for "Being a dick is in fact against the server rules." by admin "NoodleArms"',
            ],
        ),
    ],
)
def test_list_conversion(raw, expected):
    pass


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "2021.12.09-16.40.08",
            datetime(year=2021, month=12, day=9, hour=16, minute=40, second=8),
        )
    ],
)
def test_ban_list_timestamp_conversion(raw, expected):
    assert AsyncRcon.parse_ban_log_timestamp(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            '76561199023367826 : nickname "(WTH) Abu" banned for 2 hours on 2021.12.09-16.40.08 for "Being a troll" by admin "Some Admin Name"',
            BanType(
                steam_id_64="76561199023367826",
                player_name="(WTH) Abu",
                duration_hours=2,
                timestamp=datetime(
                    year=2021, month=12, day=9, hour=16, minute=40, second=8
                ),
                reason="Being a troll",
                admin="Some Admin Name",
            ),
        )
    ],
)
def test_ban_parsing(raw, expected):
    assert AsyncRcon.parse_ban_log(raw) == expected
