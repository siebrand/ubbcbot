"""The arguments of /instant_order: <supplier> <offer name> <price> <customer> [box_size] (instant-orders-design.md).

Pure parsing: no database and no Telegram. Name, supplier and customer may be quoted, with straight quotes or the
curly quotes Telegram clients insert. Without quotes the grammar is read from the end: a bare whole number after the
customer is the box size when the word three places from the end is a price; otherwise the last word is the customer
and the box size is 1. Everything between the supplier and the price is the name.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MIN_BOX_SIZE = 1
MAX_BOX_SIZE = 6

_TOKEN = re.compile(r'"([^"]*)"|“([^”]*)”|(\S+)')
_PRICE = re.compile(r"^\d+([.,]\d{1,2})?$")
# A box size is a short bare number; a longer one (a customer ID prefix) is the customer
_BOX_SIZE = re.compile(r"^\d{1,2}$")


@dataclass(frozen=True)
class InstantOrderInput:
    supplier: str
    offer_name: str
    price: Decimal
    customer: str
    box_size: int


class InstantOrderInputError(ValueError):
    """The arguments cannot be read; ``key`` is the translation key of the message for the admin"""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


@dataclass(frozen=True)
class _Token:
    text: str
    quoted: bool


def _tokens(words: list[str]) -> list[_Token]:
    tokens = []
    for straight, curly, bare in _TOKEN.findall(" ".join(words)):
        quoted = bare == ""
        tokens.append(_Token(straight or curly if quoted else bare, quoted))
    return tokens


def _price(token: _Token) -> Decimal | None:
    """A positive price with at most two decimals (a comma is a decimal sign too), or None"""
    if token.quoted or not _PRICE.match(token.text):
        return None
    try:
        price = Decimal(token.text.replace(",", "."))
    except InvalidOperation:
        return None
    return price if price > 0 else None


def parse_instant_order(words: list[str]) -> InstantOrderInput:
    """The arguments as the router split them on spaces; raises InstantOrderInputError"""
    tokens = _tokens(words)
    if len(tokens) < 4:
        raise InstantOrderInputError("usage_instant_order")

    last = tokens[-1]
    if len(tokens) >= 5 and not last.quoted and _BOX_SIZE.match(last.text) and _price(tokens[-3]) is not None:
        box_size = int(last.text)
        if not MIN_BOX_SIZE <= box_size <= MAX_BOX_SIZE:
            raise InstantOrderInputError("instant_order_box_size_invalid")
        name_tokens, price_token, customer = tokens[1:-3], tokens[-3], tokens[-2]
    else:
        box_size = MIN_BOX_SIZE
        name_tokens, price_token, customer = tokens[1:-2], tokens[-2], tokens[-1]

    price = _price(price_token)
    if price is None:
        raise InstantOrderInputError("instant_order_price_invalid")
    name = " ".join(token.text for token in name_tokens).strip()
    if not name or not tokens[0].text.strip() or not customer.text.strip():
        raise InstantOrderInputError("usage_instant_order")
    return InstantOrderInput(
        supplier=tokens[0].text.strip(),
        offer_name=name,
        price=price.quantize(Decimal("0.01")),
        customer=customer.text.strip(),
        box_size=box_size,
    )
