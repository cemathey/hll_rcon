import pytest

from hll_rcon.connection import HllConnection, _player_info_validator


@pytest.mark.parametrize("timeout, expected", [(1.0, 1.0)])
def test_validate_timeout(timeout, expected):
    assert HllConnection._validate_timeout(timeout) == expected


@pytest.mark.parametrize("timeout, expected", [("a", ValueError)])
def test_validate_timeout_exceptions(timeout, expected):
    with pytest.raises(expected):
        assert HllConnection._validate_timeout(timeout)


@pytest.mark.parametrize("buffer_size, expected", [(1, 1), ("1", 1), (None, None)])
def test_validate_max_buffer_size(buffer_size, expected):
    assert HllConnection._validate_max_buffer_size(buffer_size) == expected


@pytest.mark.parametrize("buffer_size, expected", [("a", ValueError)])
def test_validate_max_buffer_size_exceptions(buffer_size, expected):
    with pytest.raises(expected):
        assert HllConnection._validate_max_buffer_size(buffer_size)


@pytest.mark.parametrize("message, xor_key, expected", [("asdf", b"XOR", b"9<6>")])
def test_xor_encode(message, xor_key, expected):
    assert HllConnection._xor_encode(message, xor_key) == expected


@pytest.mark.parametrize("cipher_text, xor_key, expected", [(b"9<6>", b"XOR", "asdf")])
def test_xor_decode(cipher_text, xor_key, expected):
    assert HllConnection._xor_decode(cipher_text, xor_key) == expected


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
            True,
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
        (
            "Name: TYLER\nsteamID64: 76561198384418739\nTeam: None\nRole: Rifleman\nKills: 0 - Deaths: 0\nScore: C 0, O 0, D 0, S 0\nLevel: 31\n",
            "TYLER",
            True,
        ),
    ],
)
def test_validator_player_info(raw, player_name, expected):
    assert _player_info_validator(raw, player_name) == expected
