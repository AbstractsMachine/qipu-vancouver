"""What changes from one city's records to another's.

The pipeline is the same for every city. A city brings its own prompt (the body's name, its kinds of legislation, local
examples), its currency, the archive.org collection its minutes are in, and its privacy embargo: how many years must
pass before the names of private people in sensitive matters are shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class City:
    """One city's settings: the body whose minutes are read, its currency, its archive.org collection and
    its privacy embargo."""

    key: str
    name: str
    body: str
    currency: str
    embargo_years: int
    """Records younger than this many years have private people's names withheld in sensitive matters."""
    collection: str
    """The archive.org collection that holds the scanned minutes."""
    archive: str
    """Who holds and scanned the originals."""
    prompt_file: str

    def system_prompt(self) -> str:
        return resources.files("qipu_records.read").joinpath("prompts", self.prompt_file).read_text(encoding="utf-8")


VANCOUVER = City(
    key="vancouver",
    name="Vancouver",
    body="Vancouver City Council",
    currency="CAD",
    embargo_years=100,
    collection="cityofvancouvercouncilminutes",
    archive="City of Vancouver Archives",
    prompt_file="vancouver.txt",
)

SAN_FRANCISCO = City(
    key="san_francisco",
    name="San Francisco",
    body="San Francisco Board of Supervisors",
    currency="USD",
    embargo_years=75,
    collection="sanfranciscopubliclibrary",
    archive="San Francisco Public Library",
    prompt_file="san_francisco.txt",
)

CITIES = {city.key: city for city in (VANCOUVER, SAN_FRANCISCO)}


def get_city(key: str) -> City:
    """The City for a key such as "vancouver"; ValueError, naming the known keys, when there is none."""
    try:
        return CITIES[key]
    except KeyError:
        raise ValueError(f"unknown city {key!r}; known: {', '.join(sorted(CITIES))}") from None
