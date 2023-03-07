from datetime import datetime

import pytest

from async_hll_rcon.io import AsyncRcon, HllConnection
from async_hll_rcon.typedefs import (
    PermanentBanType,
    PlayerInfo,
    Score,
    TemporaryBanType,
)


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
            TemporaryBanType(
                steam_id_64="76561199023367826",
                player_name="(WTH) Abu",
                duration_hours=2,
                timestamp=datetime(
                    year=2021, month=12, day=9, hour=16, minute=40, second=8
                ),
                reason="Being a troll",
                admin="Some Admin Name",
            ),
        ),
        (
            '76561199023367826 : banned for 2 hours on 2021.12.09-16.40.08 for "Being a troll" by admin "Some Admin Name"',
            TemporaryBanType(
                steam_id_64="76561199023367826",
                player_name=None,
                duration_hours=2,
                timestamp=datetime(
                    year=2021, month=12, day=9, hour=16, minute=40, second=8
                ),
                reason="Being a troll",
                admin="Some Admin Name",
            ),
        ),
    ],
)
def test_temp_ban_parsing(raw, expected):
    assert AsyncRcon.parse_temp_ban_log(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            '76561197975123456 : nickname "Georgij Zhukov Sovie" banned on 2022.12.06-16.27.14 for "Racism" by admin "BLACKLIST: NoodleArms"',
            PermanentBanType(
                steam_id_64="76561197975123456",
                player_name="Georgij Zhukov Sovie",
                timestamp=datetime(
                    year=2022, month=12, day=6, hour=16, minute=27, second=14
                ),
                reason="Racism",
                admin="BLACKLIST: NoodleArms",
            ),
        ),
        (
            '76561197975123456 : banned on 2022.12.06-16.27.14 for "Racism" by admin "BLACKLIST: NoodleArms"',
            PermanentBanType(
                steam_id_64="76561197975123456",
                player_name=None,
                timestamp=datetime(
                    year=2022, month=12, day=6, hour=16, minute=27, second=14
                ),
                reason="Racism",
                admin="BLACKLIST: NoodleArms",
            ),
        ),
    ],
)
def test_perma_ban_parsing(raw, expected):
    assert AsyncRcon.parse_perma_ban_log(raw) == expected


@pytest.mark.parametrize(
    "raw, expected", [("1,2,3,4", "1,2,3,4"), ([(0, 1), (2, 3)], "0,1,2,3")]
)
def test_convert_vote_kick_thresholds(raw, expected):
    assert AsyncRcon.convert_vote_kick_thresholds(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("1,2,3", ValueError), ((0,), ValueError), ("", ValueError), (None, ValueError)],
)
def test_convert_vote_kick_thresholds_exceptions(raw, expected):
    with pytest.raises(expected):
        AsyncRcon.convert_vote_kick_thresholds(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            """Name: NoodleArms
steamID64: 76561198004895814
Team: None
Role: Rifleman
Kills: 0 - Deaths: 0
Score: C 0, O 0, D 0, S 0
Level: 238
""",
            PlayerInfo(
                player_name="NoodleArms",
                steam_id_64="76561198004895814",
                team=None,
                role="Rifleman",
                score=Score(
                    kills=0, deaths=0, combat=0, offensive=0, defensive=0, support=0
                ),
                level=238,
            ),
        )
    ],
)
def test_parse_player_info(raw, expected):
    assert AsyncRcon.parse_player_info(raw) == expected
