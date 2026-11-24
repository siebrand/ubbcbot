"""Cleaning of typed offer names"""

# Double quote marks of every kind: straight, curly (either direction, as Telegram clients mix them up) and low-9
QUOTE_CHARS = '"“”„‟'


def clean_offer_name(name: str | None) -> str:
    """The name without spaces and without double quote marks at its start and end (quotes inside stay)"""
    return (name or "").strip().strip(QUOTE_CHARS).strip()
