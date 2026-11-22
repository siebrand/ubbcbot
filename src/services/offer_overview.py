"""The overview of /offer_overview: the offers that can be ordered, grouped by the style in their name.

The style is a part of the offer name in parentheses, such as "(NEIPA)" or "(SOUR / NEIPA)": every word in it,
separated by "/", is a style of STYLE_GROUPS (not case-sensitive). "(BA)X" is barrel aged and plain X in one offer,
style X, as in "((BA)OATMEALSTOUT)"; "BA" on its own marks barrel aged and is no style. Other parts in parentheses
("(Blend No. 3)", "(2025)") are not a style. The first style decides the group; an offer without a style is in the
last group, "other". Only the groups and the numbers live here; handlers/admin/offer/overview.py formats and sends
the list.
"""

from collections.abc import Iterable

# The groups of the overview in their order (the key of each group's heading is offer_overview_group_<key>), each
# with its styles (owner, 2026-11-22). A new style is one word in this table.
STYLE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "ipa",
        (
            "TIPA",
            "IPA",
            "DIPA",
            "PALE",
            "NEIPA",
            "NEDIPA",
            "ULTRA",
            "NETIPA",
            "XIPA",
            "WCIPA",
            "BDIPA",
            "APA",
            "HYPER",
            "ULTRA TIPA",
            "PILS",
            "LAGER",
            "BITTER",
        ),
    ),
    ("smoothie_sour", ("SMOOTHIE", "SOUR", "NASMOOTHIE", "PASTRYSOUR", "FRUITEDSOUR", "GOSE")),
    (
        "dark",
        (
            "BAIMPSTOUT",
            "IMPSTOUT",
            "CUSTARDALE",
            "BABARLEYWINE",
            "PASTRYSTOUT",
            "PASTRY",
            "BASTOUT",
            "BAEXTRASTOUT",
            "MILKSTOUT",
            "OATMEALSTOUT",
            "INDOSTOUT",
            "IMPPORTER",
            "DBPORTER",
            "BARLEYWINE",
            "BABARLEY",
            "DBABARLEYWINE",
            "BAQUAD",
            "BAQUINT",
        ),
    ),
    (
        "wild",
        (
            "WILD",
            "MIXED",
            "MIXEDFERM",
            "PEATEDMIXEDFERM",
            "GRAPEMIXEDFERM",
            "FLANDERSRED",
            "FARMHOUSE",
            "GRISETTE",
            "SAISON",
            "BASAISON",
            "BABLACKSOUR",
            "GRAPEALE",
        ),
    ),
    # Known styles without a group of their own, so that "(AMBER / SOUR)" counts as a style
    ("other", ("ALE", "AMBER", "STRONGALE", "CIDER", "MEDE", "TOMATEN", "DIV", "DIVDUITS", "DIVERSEBA")),
)
OTHER = "other"
GROUP_ORDER = tuple(key for key, _ in STYLE_GROUPS)

_GROUP_OF_STYLE = {style: key for key, styles in STYLE_GROUPS for style in styles}
# "(BA)X": barrel aged and plain X; "BA" alone: barrel aged
BARREL_AGED_PREFIX = "(BA)"
BARREL_AGED = "BA"


def _parts_in_parentheses(name: str) -> list[str]:
    """The text of every outermost pair of parentheses, nested ones kept: "a ((BA)X) (b)" → ["(BA)X", "b"]"""
    parts: list[str] = []
    depth, start = 0, 0
    for position, character in enumerate(name):
        if character == "(":
            if depth == 0:
                start = position + 1
            depth += 1
        elif character == ")" and depth:
            depth -= 1
            if depth == 0:
                parts.append(name[start:position])
    return parts


def _styles(part: str) -> list[str] | None:
    """The styles of a part in parentheses, or None when it is not (all) styles"""
    styles = []
    for word in part.split("/"):
        style = word.strip().upper()
        if style.startswith(BARREL_AGED_PREFIX):
            style = style[len(BARREL_AGED_PREFIX) :].strip()
        if style == BARREL_AGED:
            continue
        if style not in _GROUP_OF_STYLE:
            return None
        styles.append(style)
    return styles or None


def style_group(name: str) -> str:
    """The group of an offer name: that of the first style in the first part in parentheses that is all styles"""
    for part in _parts_in_parentheses(name or ""):
        styles = _styles(part)
        if styles:
            return _GROUP_OF_STYLE[styles[0]]
    return OTHER


def grouped(offers: Iterable) -> list[tuple[str, list]]:
    """(group, offers) for every group that has offers, in GROUP_ORDER, the offers lowest number first"""
    groups: dict[str, list] = {}
    for offer in offers:
        groups.setdefault(style_group(offer.name), []).append(offer)
    return [(key, sorted(groups[key], key=lambda offer: offer.offer_id)) for key in GROUP_ORDER if key in groups]


def can_still_be_ordered(boxes: list) -> int | None:
    """How many units can still be ordered: the room left in the offer's boxes. None when there is none to show:
    before the offer has a box, or when every box is full (an active offer without room is sold out, otherwise the
    next order opens a new box)."""
    room = sum(max(box.max_capacity - box.current_quantity, 0) for box in boxes)
    return room or None
