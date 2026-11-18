"""Which offers each /list_offers view shows, in which order, and how much of an offer is ordered."""

import pytest

from models.entities import Box, Offer, Order
from services import offer_listing
from services.offer_listing import ADMIN_VIEWS, DEFAULT_VIEW, admin_view


def offer(offer_id, status):
    return Offer(offer_id=offer_id, status=status)


OFFERS = [
    offer(5, "active"),
    offer(2, "draft"),
    offer(3, "active"),
    offer(7, "sold_out"),
    offer(1, "inactive"),
    offer(4, "import"),
    offer(6, "completed"),
]


class TestViews:
    @pytest.mark.parametrize("word", [None, "", "bogus", "user"])
    def test_no_or_an_unknown_word_is_the_default_overview(self, word):
        assert admin_view(word) is DEFAULT_VIEW

    def test_the_default_overview_is_work_in_progress_with_sections(self):
        assert DEFAULT_VIEW.statuses == ("draft", "import", "active")
        assert DEFAULT_VIEW.sections is True

    def test_only_the_overviews_have_sections(self):
        assert {word for word, view in ADMIN_VIEWS.items() if view.sections} == {"all"}

    def test_single_status_views_without_a_title_key_have_one_status(self):
        for view in ADMIN_VIEWS.values():
            if view.title_key is None:
                assert len(view.statuses) == 1

    def test_every_status_of_a_view_has_an_icon_and_a_header(self):
        for view in [DEFAULT_VIEW, *ADMIN_VIEWS.values()]:
            for status in view.statuses:
                assert status in offer_listing.STATUS_ICONS
                assert status in offer_listing.SECTION_TITLE_KEYS or status in offer_listing.STATUS_LABEL_KEYS

    def test_offers_in_a_view_by_status_then_id(self):
        listed = offer_listing.offers_in_view(OFFERS, ADMIN_VIEWS["all"])

        assert [(status, o.offer_id) for status, o in listed] == [
            ("draft", 2),
            ("import", 4),
            ("active", 3),
            ("active", 5),
            ("sold_out", 7),
            ("completed", 6),
            ("inactive", 1),
        ]

    def test_customers_see_active_offers_newest_first(self):
        assert [o.offer_id for o in offer_listing.customer_offers(OFFERS)] == [5, 3]

    def test_sold_out_offers_by_id(self):
        assert [o.offer_id for o in offer_listing.sold_out_offers([*OFFERS, offer(0, "sold_out")])] == [0, 7]


class TestOrdered:
    def test_before_delivery_the_open_orders_count_against_every_box(self):
        boxes = [Box(max_capacity=12, status="ordered"), Box(max_capacity=6, status="open")]

        assert offer_listing.ordered_and_capacity(boxes, [Order(quantity=5), Order(quantity=2)]) == (7, 18)

    def test_after_delivery_only_delivered_boxes_count_with_what_is_in_them(self):
        boxes = [
            Box(max_capacity=12, current_quantity=10, status="delivered"),
            Box(max_capacity=6, current_quantity=1, status="open"),
        ]

        assert offer_listing.ordered_and_capacity(boxes, [Order(quantity=99)]) == (10, 12)

    def test_without_boxes(self):
        assert offer_listing.ordered_and_capacity([], []) == (0, 0)

    def test_a_box_ordered_at_the_wholesaler(self):
        assert offer_listing.has_ordered_box([Box(status="open"), Box(status="ordered")])
        assert not offer_listing.has_ordered_box([Box(status="full")])

    def test_grouped_by_offer(self):
        grouped = offer_listing.by_offer(
            [Box(box_id="a", offer_id=1), Box(box_id="b", offer_id=2), Box(box_id="c", offer_id=1)]
        )

        assert {k: [b.box_id for b in v] for k, v in grouped.items()} == {1: ["a", "c"], 2: ["b"]}
