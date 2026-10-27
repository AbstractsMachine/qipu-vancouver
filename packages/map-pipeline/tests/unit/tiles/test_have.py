import base64

import pytest

from qipu_map.tiles.have import Have, pack_have, unpack_have


def test_packing_follows_the_contract_bit_order() -> None:
    have = pack_have({(1, 0), (3, 1)})
    assert (have["x0"], have["y0"], have["cols"], have["rows"]) == (1, 0, 3, 2)
    assert base64.b64decode(have["bits"]) == bytes([0b10000100])


def test_the_contract_example_decodes() -> None:
    have = Have(x0=1, y0=0, cols=6, rows=4, bits="/38P")
    tiles = unpack_have(have)
    assert len(tiles) == 19
    assert (1, 0) in tiles
    assert (6, 3) in tiles
    assert pack_have(tiles) == have


def test_round_trip_on_a_ragged_shape() -> None:
    tiles = {(x, y) for x in range(5, 17) for y in range(2, 9) if (x * 7 + y * 3) % 4}
    assert unpack_have(pack_have(tiles)) == tiles


def test_empty_and_wrong_length() -> None:
    with pytest.raises(ValueError, match="at least one"):
        pack_have([])
    with pytest.raises(ValueError, match="bytes"):
        unpack_have(Have(x0=0, y0=0, cols=9, rows=1, bits="AA=="))
