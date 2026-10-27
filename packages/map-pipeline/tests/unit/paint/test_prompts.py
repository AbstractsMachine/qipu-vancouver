import numpy as np
import pytest

from qipu_map.classes import SurfaceClass as C
from qipu_map.paint.prompts import LEAD, Choice, Content, Key, PromptSet, choose

NO_BUILDING_WORDS = ("build", "house", "roof", "wall", "tower", "street", "storey", "water", "garden", "lawn")


def tile(**shares: float) -> np.ndarray:
    """A 100 x 100 class tile with the given shares (rest ground)."""
    out = np.full(10_000, C.GROUND, np.uint8)
    i = 0
    for name, share in shares.items():
        n = round(share * 10_000)
        out[i : i + n] = C[name.upper()]
        i += n
    return out.reshape(100, 100)


@pytest.fixture(scope="module")
def prompts() -> PromptSet:
    return PromptSet.load("vancouver")


def test_choice_follows_the_class_pass() -> None:
    assert choose(Content.measure(tile(water=0.97))) is None
    assert choose(Content.measure(tile(water=0.4, grass=0.5))) == Choice(Key.SHORE, False)
    assert choose(Content.measure(tile(sand=0.2, grass=0.5))) == Choice(Key.BEACH, False)
    assert choose(Content.measure(tile(tree=0.7))) == Choice(Key.WOODS, False)
    assert choose(Content.measure(tile(grass=0.6, roof=0.05))) == Choice(Key.MEADOW, False)
    assert choose(Content.measure(tile(roof=0.3, road=0.3))) == Choice(Key.BASE, False)
    assert choose(Content.measure(tile(wall=0.3, roof=0.2, rail=0.02))) == Choice(Key.TOWERS, True)


def test_open_keys_name_no_building_and_no_water(prompts: PromptSet) -> None:
    for key in (Key.MEADOW, Key.WOODS, Key.BEACH):
        for year in (2026, 1950):
            text = (
                prompts.text(Choice(key, False), year, 2026).lower().replace("seawall", "").replace("understorey", "")
            )
            assert not [w for w in NO_BUILDING_WORDS if w in text], (key, year)


def test_texts_and_eras(prompts: PromptSet) -> None:
    today = prompts.text(Choice(Key.TOWERS, True), 2026, 2026)
    assert "glass curtain walls" in today
    assert "railway tracks" in today
    assert "lush" not in today
    early = prompts.text(Choice(Key.TOWERS, False), 1930, 2026)
    assert "in 1930" in early
    assert "glass" not in early
    assert "deep green" in early
    late = prompts.text(Choice(Key.TOWERS, False), 1972, 2026)
    assert "of the 1960s" in late
    assert "the 1960s and 1970s" in prompts.text(Choice(Key.TOWERS, False), 1982, 2026)
    assert "in 1950: nothing modern" in prompts.text(Choice(Key.MEADOW, False), 1950, 2026)
    assert "lush" not in prompts.text(Choice(Key.BEACH, False), 2026, 2026)
    assert "English Bay" in prompts.text(Choice(Key.SHORE, False), 1950, 2026)
    base = prompts.text(Choice(Key.BASE, False), 1950, 2026)
    assert base == prompts.text(Choice(Key.BASE, False), 2026, 2026)
    for key in Key:
        assert prompts.text(Choice(key, False), 2026, 2026).startswith(LEAD)


def test_no_san_francisco_in_vancouver_prompts(prompts: PromptSet) -> None:
    text = " ".join(prompts.parts.values()).lower()
    for word in ("san francisco", "bay bridge", "cable car", "victorian", "california", "helicopter"):
        assert word not in text


def test_anchored_prompt(prompts: PromptSet) -> None:
    a = prompts.anchored(prompts.text(Choice(Key.BASE, False), 2026, 2026))
    assert a.startswith("Turn image 1, a soft aerial photograph")
    assert "geometry of image 2" in a
    with pytest.raises(ValueError, match="lead"):
        prompts.anchored("Paint a map")


def test_unknown_city(tmp_path: object) -> None:
    with pytest.raises(FileNotFoundError):
        PromptSet.load("atlantis")
