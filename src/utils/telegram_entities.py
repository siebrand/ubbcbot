"""Telegram message entities (the formatting a user applied in their client) as HTML"""

import html

TAGS = {"bold": "b", "italic": "i", "spoiler": "tg-spoiler"}


def entities_to_html(text: str, entities: list) -> str:
    """Convert Telegram message entities to HTML format

    Telegram counts offsets and lengths in UTF-16 code units, so an emoji outside the basic plane (🍺) counts as two.
    The text between the tags is escaped; without entities the text is returned as it is.
    """
    if not entities:
        return text

    # (position, order, tag): at one position close tags come before open tags; the longer entity opens first and
    # closes last, so nested entities stay nested
    events = []
    for index, entity in enumerate(entities):
        tag = TAGS.get(entity["type"])
        if not tag or entity["length"] <= 0:
            continue
        start = entity["offset"]
        end = start + entity["length"]
        events.append((start, 1, -end, index, f"<{tag}>"))
        events.append((end, 0, -start, -index, f"</{tag}>"))
    events.sort()

    units = text.encode("utf-16-le")
    result = []
    position = 0
    for offset, *_, tag in events:
        result.append(_escaped(units, position, offset))
        result.append(tag)
        position = offset
    result.append(_escaped(units, position, len(units) // 2))
    return "".join(result)


def _escaped(units: bytes, start: int, end: int) -> str:
    """The text between two UTF-16 offsets, escaped for parse_mode=HTML"""
    return html.escape(units[2 * start : 2 * end].decode("utf-16-le"), quote=False)
