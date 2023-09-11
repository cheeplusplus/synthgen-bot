from typing import Optional
from discord import Embed
import re
import requests
from .scryfall_types import ScryfallCard

# Keep a cache of cards fetched just to be safe
CARD_CACHE: dict[str, ScryfallCard] = {}


async def get_mtg_embeds_from_message(message: str) -> Optional[list[Embed]]:
    """Find and return Discord embeds for any MTG cards found in the message body."""
    if not message:
        return None

    matches = re.findall("\[\[([^\[]+)\]\]", message)
    if len(matches) < 1:
        return None

    results = []
    for card_name in matches:
        if len(results) > 9:
            # Only return the first 10 results
            break

        embed = await get_mtg_embed_for_card_name(card_name)
        if embed:
            results.append(embed)

    if len(results) < 1:
        return None

    return results


async def get_mtg_embed_for_card_name(card_name: str) -> Optional[Embed]:
    """Search for and return a Discord embed for an MTG card by name."""
    if card_name.lower() in CARD_CACHE:
        # Pull the card from the cache
        card = CARD_CACHE[card_name.lower()]
    else:
        # Search for the card
        try:
            card = await get_card_by_fuzzy_match(card_name)
        except requests.exceptions.HTTPError as e:
            print(f"Got error while looking up [[{card_name}]]:", repr(e))
            return None

        # Cache both the fuzzy name and the real name
        CARD_CACHE[card_name.lower()] = card
        CARD_CACHE[card.name.lower()] = card

    em = Embed(title=f"{card.name} {card.mana_cost}", url=card.scryfall_uri)
    em.add_field(name="Type", value=card.type_line, inline=False).add_field(
        name="Oracle text", value=card.oracle_text, inline=False
    )

    if card.power or card.toughness:
        em.add_field(
            name="Power/Toughness",
            value=f"`{card.power} / {card.toughness}`",
            inline=False,
        )
    if card.loyalty:
        em.add_field(name="Loyalty", value=card.loyalty, inline=False)
    if card.image_uris and "normal" in card.image_uris:
        em.set_thumbnail(url=card.image_uris["normal"])

    return em


async def get_card_by_fuzzy_match(card_name: str) -> ScryfallCard:
    print(f"Looking up on Scryfall for a card named [[{card_name}]]")

    req = requests.get(
        "https://api.scryfall.com/cards/named", params={"fuzzy": card_name}
    )
    req.raise_for_status()

    res = req.json()
    card = ScryfallCard.from_json(res)
    return card
