"""Telegram message entities (the formatting a user applied in their client) as HTML"""


def entities_to_html(text: str, entities: list) -> str:
    """Convert Telegram message entities to HTML format"""
    if not entities:
        return text

    # Sort entities by offset in reverse order to avoid offset shifts
    sorted_entities = sorted(entities, key=lambda x: x["offset"], reverse=True)

    result = text
    for entity in sorted_entities:
        start = entity["offset"]
        length = entity["length"]
        end = start + length
        entity_text = text[start:end]

        if entity["type"] == "bold":
            result = result[:start] + f"<b>{entity_text}</b>" + result[end:]
        elif entity["type"] == "italic":
            result = result[:start] + f"<i>{entity_text}</i>" + result[end:]
        elif entity["type"] == "spoiler":
            result = result[:start] + f"<tg-spoiler>{entity_text}</tg-spoiler>" + result[end:]

    return result
