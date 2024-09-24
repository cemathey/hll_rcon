from datetime import datetime

import pytest

from hll_rcon.response_types import PermanentBan, TemporaryBan


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            TemporaryBan(
                player_id="76561198004123456",
                player_name=None,
                duration_hours=2,
                ban_timestamp=datetime(
                    year=2023, month=3, day=6, hour=13, minute=44, second=32
                ),
                reason=None,
                admin=None,
            ),
            "76561198004123456 : banned for 2 hours on 2023.03.06-13.44.32",
        ),
        (
            TemporaryBan(
                player_id="76561198004123456",
                player_name="NoodleArms",
                duration_hours=2,
                ban_timestamp=datetime(
                    year=2023, month=3, day=6, hour=13, minute=44, second=32
                ),
                reason=None,
                admin=None,
            ),
            '76561198004123456 : nickname "NoodleArms" banned for 2 hours on 2023.03.06-13.44.32',
        ),
        (
            TemporaryBan(
                player_id="76561198004123456",
                player_name="",
                duration_hours=2,
                ban_timestamp=datetime(
                    year=2023, month=3, day=6, hour=15, minute=23, second=26
                ),
                reason=None,
                admin=None,
            ),
            "76561198004123456 : banned for 2 hours on 2023.03.06-15.23.26",
        ),
    ],
)
def test_temp_ban_log_to_str(raw, expected):
    assert TemporaryBan.temp_ban_log_to_str(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            PermanentBan(
                player_id="76561198004123456",
                player_name=None,
                ban_timestamp=datetime(
                    year=2023, month=3, day=6, hour=13, minute=44, second=32
                ),
                reason=None,
                admin=None,
            ),
            "76561198004123456 : banned on 2023.03.06-13.44.32",
        ),
        (
            PermanentBan(
                player_id="76561198004123456",
                player_name="NoodleArms",
                ban_timestamp=datetime(
                    year=2023, month=3, day=6, hour=13, minute=44, second=32
                ),
                reason=None,
                admin=None,
            ),
            '76561198004123456 : nickname "NoodleArms" banned on 2023.03.06-13.44.32',
        ),
        (
            PermanentBan(
                player_id="76561198004123456",
                player_name="",
                ban_timestamp=datetime(
                    year=2023, month=3, day=6, hour=15, minute=23, second=26
                ),
                reason=None,
                admin=None,
            ),
            "76561198004123456 : banned on 2023.03.06-15.23.26",
        ),
    ],
)
def test_perma_ban_log_to_str(raw, expected):
    assert PermanentBan.perma_ban_log_to_str(raw) == expected
