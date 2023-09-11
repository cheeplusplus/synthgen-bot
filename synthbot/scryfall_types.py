from typing import Optional
from attrs import define, field
import cattrs


@define
class ScryfallCard:
    name: str = field()
    scryfall_uri: str = field()
    mana_cost: Optional[str] = field(default=None)
    type_line: Optional[str] = field(default=None)
    oracle_text: Optional[str] = field(default=None)
    power: Optional[str] = field(default=None)
    toughness: Optional[str] = field(default=None)
    loyalty: Optional[str] = field(default=None)
    image_uris: Optional[dict[str, str]] = field(default=None)

    @classmethod
    def from_json(cl, data):
        return cattrs.structure(data, cl)
