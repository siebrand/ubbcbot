"""The /instant_order arguments (instant-orders-design.md, IO-3)"""

from decimal import Decimal

import pytest

from services.instant_order_input import InstantOrderInput, InstantOrderInputError, parse_instant_order


def parse(line: str) -> InstantOrderInput:
    return parse_instant_order(line.split())  # the router splits the command on spaces


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Brouwerij Pils 2.50 Jan", ("Brouwerij", "Pils", Decimal("2.50"), "Jan", 1)),
        ("Brouwerij Pils 2.50 Jan 4", ("Brouwerij", "Pils", Decimal("2.50"), "Jan", 4)),
        ("Brouwerij Westmalle Tripel 2.50 Jan", ("Brouwerij", "Westmalle Tripel", Decimal("2.50"), "Jan", 1)),
        (
            '"De Molen" "Hel & Verdoemenis" 4 "Jan Jansen" 6',
            ("De Molen", "Hel & Verdoemenis", Decimal("4"), "Jan Jansen", 6),
        ),
        ("“De Molen” “Op & Top” 3,75 “Jan Jansen”", ("De Molen", "Op & Top", Decimal("3.75"), "Jan Jansen", 1)),
        ("Brouwerij Tripel 8 2.50 Jan", ("Brouwerij", "Tripel 8", Decimal("2.50"), "Jan", 1)),
        ("Brouwerij Tripel 8 2.50 Jan 3", ("Brouwerij", "Tripel 8", Decimal("2.50"), "Jan", 3)),
        ("Brouwerij Pils 2,5 Jan", ("Brouwerij", "Pils", Decimal("2.50"), "Jan", 1)),
        ("Brouwerij Pils 2.50 12345678", ("Brouwerij", "Pils", Decimal("2.50"), "12345678", 1)),
        ("Brouwerij Tripel 8 2.50 12345678", ("Brouwerij", "Tripel 8", Decimal("2.50"), "12345678", 1)),
        ("Brouwerij Pils 2.50 12345678 2", ("Brouwerij", "Pils", Decimal("2.50"), "12345678", 2)),
        ('Brouwerij Pils 2.50 "4"', ("Brouwerij", "Pils", Decimal("2.50"), "4", 1)),  # a quoted customer is a name
        # Quote marks at the ends of the name never end up in it: wrong-direction curly quotes, a lone opening quote
        ("“Brew Your Mind“ Pils 5 Jan", ("Brew Your Mind", "Pils", Decimal("5"), "Jan", 1)),
        ('Brouwerij "Hel & Verdoemenis 4.50 Jan', ("Brouwerij", "Hel & Verdoemenis", Decimal("4.50"), "Jan", 1)),
        ("Brouwerij “Hel & Verdoemenis“ 4.50 Jan", ("Brouwerij", "Hel & Verdoemenis", Decimal("4.50"), "Jan", 1)),
        (
            '"De Molen" "Hel & Verdoemenis 4.50 "Jan Jansen"',
            ("De Molen", "Hel & Verdoemenis", Decimal("4.50"), "Jan Jansen", 1),
        ),
        (
            'Kaapse "Gozer Oak Aged (2014) (750ml)" 10 Jan',
            ("Kaapse", "Gozer Oak Aged (2014) (750ml)", Decimal("10"), "Jan", 1),
        ),
    ],
)
def test_valid_arguments(line, expected):
    result = parse(line)

    assert (result.supplier, result.offer_name, result.price, result.customer, result.box_size) == expected


def test_the_price_has_two_decimals():
    assert str(parse("Brouwerij Pils 4 Jan").price) == "4.00"


@pytest.mark.parametrize(
    "line, key",
    [
        ("", "usage_instant_order"),
        ("Brouwerij Pils 2.50", "usage_instant_order"),
        ("Brouwerij Pils 2.505 Jan", "instant_order_price_invalid"),
        ("Brouwerij Pils 0 Jan", "instant_order_price_invalid"),
        ("Brouwerij Pils 0.00 Jan", "instant_order_price_invalid"),
        ("Brouwerij Pils -2 Jan", "instant_order_price_invalid"),
        ("Brouwerij Pils gratis Jan", "instant_order_price_invalid"),
        ('Brouwerij Pils "2.50" Jan', "instant_order_price_invalid"),  # a quoted token is never a price
        ("Brouwerij Pils 2.50 Jan 0", "instant_order_box_size_invalid"),
        ("Brouwerij Pils 2.50 Jan 7", "instant_order_box_size_invalid"),
        ("Brouwerij Pils 2.50 Jan x", "instant_order_price_invalid"),  # x is read as the customer: Jan is no price
        ("Brouwerij Pils 2.50 Jan Jansen", "instant_order_price_invalid"),  # an unquoted customer with a space
    ],
)
def test_invalid_arguments(line, key):
    with pytest.raises(InstantOrderInputError) as error:
        parse(line)

    assert error.value.key == key
