import pytest

from async_hll_rcon.connection import _validator_player_info


@pytest.mark.parametrize(
    "raw, player_name, expected",
    [
        (
            "Name: ChrisFul\nsteamID64: 76561197978189125\nTeam: Allies\nRole: Rifleman\nLoadout: Standard Issue\nKills: 0 - Deaths: 0\nScore: C 0, O 0, D 0, S 0\nLevel: 211\n",
            "ChrisFul",
            True,
        ),
        (
            "Name: ChrisFul\nsteamID64: 76561197978189125\nTeam: Allies\nRole: Rifleman\nLoadout: Standard Issue\nKills: 0 - Deaths: 0\nScore: C 0, O 0, D 0, S 0\nLevel: 211",
            "ChrisFul",
            False,
        ),
        (
            "Name: SunsetDrive24K\nsteamID64: 76561198288202412\nTeam: Axis\nRole: HeavyMachineGunner\nUnit: 8 - ITEM\nLoadout: Veteran\nKills: 5 - Deaths: 4\nScore: C 36, O 220, D 60, S 0\nLevel: 52\n",
            "SunsetDrive24K",
            True,
        ),
        (
            "Name: Sin\nsteamID64: 76561198857879516\nTeam: Allies\nRole: Medic\nUnit: 6 - GEORGE\nLoadout: Standard Issue\nKills: 0 - Deaths: 0\nScore: C 0, O 0, D 0, S 0\nLevel: 44\n",
            "Sin",
            True,
        ),
    ],
)
def test_validator_player_info(raw, player_name, expected):
    assert _validator_player_info(raw, player_name) == expected
