import pytest

from async_hll_rcon.io import AsyncRcon


@pytest.mark.parametrize("message, xor_key, expected", [("asdf", b"XOR", b"9<6>")])
def test_xor_encode(message, xor_key, expected):
    assert AsyncRcon._xor_encode(message, xor_key) == expected


@pytest.mark.parametrize("cipher_text, xor_key, expected", [(b"9<6>", b"XOR", "asdf")])
def test_xor_decode(cipher_text, xor_key, expected):
    assert AsyncRcon._xor_decode(cipher_text, xor_key) == expected
