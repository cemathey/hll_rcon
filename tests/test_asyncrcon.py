import pytest

from async_hll_rcon.io import AsyncRcon, HllConnection


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
