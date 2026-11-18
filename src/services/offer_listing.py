"""What the offer lists of /list_offers show: which offers per view, in which order, and how much is ordered.

Only the selection and the numbers live here; handlers/customer/info_commands.py formats and sends the lists.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from models.entities import BoxStatus, OfferStatus, OrderStatus

PAGE_SIZE = 20

DRAFT, IMPORT, ACTIVE = OfferStatus.DRAFT.value, OfferStatus.IMPORT.value, OfferStatus.ACTIVE.value
SOLD_OUT, COMPLETED, INACTIVE = OfferStatus.SOLD_OUT.value, OfferStatus.COMPLETED.value, OfferStatus.INACTIVE.value

# Orders that still take up room in a box that has not been delivered
OPEN_ORDER_STATUSES = (OrderStatus.PENDING.value, OrderStatus.ORDERED.value)


@dataclass(frozen=True)
class AdminView:
    """One of the admin's /list_offers filters.

    ``title_key`` None: the view has one status, and its section header is the title. ``sections``: every status
    gets a header of its own (the views that mix statuses for a quick overview).
    """

    statuses: tuple[str, ...]
    title_key: str | None = None
    sections: bool = False


DEFAULT_VIEW = AdminView((DRAFT, IMPORT, ACTIVE), "current_offers_admin", sections=True)
ADMIN_VIEWS = {
    "all": AdminView((DRAFT, IMPORT, ACTIVE, SOLD_OUT, COMPLETED, INACTIVE), "all_offers_admin", sections=True),
    "draft": AdminView((DRAFT,), "draft_offers"),
    "import": AdminView((IMPORT,), "import_offers"),
    "active": AdminView((ACTIVE,), "active_offers"),
    "archived": AdminView((SOLD_OUT, COMPLETED, INACTIVE), "archived_offers"),
    "completed": AdminView((COMPLETED,)),
    "inactive": AdminView((INACTIVE,)),
}

STATUS_ICONS = {DRAFT: "📝", IMPORT: "📥", ACTIVE: "🍺", SOLD_OUT: "🚫", COMPLETED: "✅", INACTIVE: "❌"}
# The header of a section: a translation for these, the icon and the status label for the others
SECTION_TITLE_KEYS = {DRAFT: "draft_offers", IMPORT: "import_offers", ACTIVE: "active_offers"}
STATUS_LABEL_KEYS = {SOLD_OUT: "status_sold_out", COMPLETED: "status_completed", INACTIVE: "status_inactive"}
# Offers whose line shows how much is ordered of how much there is
SHOWS_ORDERED = {IMPORT, ACTIVE, SOLD_OUT}
# An active offer with a box ordered at the wholesaler gets this icon in the admin's list
ORDERED_BOX_ICON = "📦🍺"


def admin_view(filter_word: str | None) -> AdminView:
    """The view of a filter word; no word or an unknown one is the default overview"""
    return ADMIN_VIEWS.get(filter_word or "", DEFAULT_VIEW)


def by_offer(items: Iterable) -> dict[int, list]:
    """Boxes or orders grouped on their offer_id"""
    grouped: dict[int, list] = {}
    for item in items:
        grouped.setdefault(item.offer_id, []).append(item)
    return grouped


def has_ordered_box(boxes: list) -> bool:
    """Whether a box of the offer is ordered at the wholesaler"""
    return any(box.status == BoxStatus.ORDERED.value for box in boxes)


def ordered_and_capacity(boxes: list, open_orders: list) -> tuple[int, int]:
    """How many units are ordered, of how many there are.

    Once boxes are delivered, only those count, with what is in them; before that, every box counts and the
    ordered units are those of the open orders.
    """
    delivered = [box for box in boxes if box.status == BoxStatus.DELIVERED.value]
    if delivered:
        return sum(box.current_quantity for box in delivered), sum(box.max_capacity for box in delivered)
    return sum(order.quantity for order in open_orders), sum(box.max_capacity for box in boxes)


def offers_in_view(offers: list, view: AdminView) -> list[tuple[str, object]]:
    """(status, offer) for every offer the view shows: by status in the order of the view, then by offer id"""
    ordered = sorted(offers, key=lambda offer: offer.offer_id)
    return [(status, offer) for status in view.statuses for offer in ordered if offer.status == status]


def customer_offers(offers: list) -> list:
    """The offers customers can order, newest first"""
    return sorted((offer for offer in offers if offer.status == ACTIVE), key=lambda o: o.offer_id, reverse=True)


def sold_out_offers(offers: list) -> list:
    return sorted((offer for offer in offers if offer.status == SOLD_OUT), key=lambda offer: offer.offer_id)
