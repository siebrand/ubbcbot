"""Builds the Telegram message (text + inline keyboard) for an offer
announcement, in its current status. Pure and side-effect-free so it can be
reused by the initial announce path and by the status/content re-sync, and
unit-tested without any Telegram or DB access.

The status is reflected by a single leading icon in the title line:
  - active     : (no icon), order buttons present
  - sold_out   : 🔴 + "sold out" suffix, no buttons
  - cancelled  : ⛔ + "cancelled" suffix, no buttons

For cancelled offers the stored status is INACTIVE, so callers pass
``cancelled=True`` explicitly.
"""

import html

from models.entities import OfferStatus

_SOLD_OUT_ICON = "🔴"
_CANCELLED_ICON = "⛔"


class OfferMessageBuilder:
    def __init__(self, bot_username: str, translate):
        self.bot_username = bot_username
        self._t = translate

    def build(self, offer, cancelled: bool = False):
        """Return (text, reply_markup) for the offer in its current state.

        reply_markup is the order keyboard for an active offer, or None when the
        offer is sold out or cancelled (buttons removed).
        """
        name = html.escape(offer.name or "")
        title = (
            f"<b><a href='https://t.me/{self.bot_username}?start=view_offer_{offer.offer_id}'>"
            f"{offer.offer_id}</a>. {name} €{offer.price_per_unit:.2f}</b>"
        )

        icon, suffix_key, active = self._state(offer, cancelled)
        if icon:
            title = f"{icon} {title} — {self._t(suffix_key)}"

        text = f"{title}\n\n{offer.description or ''}\n"

        reply_markup = None
        if active:
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": self._t("order_1"), "callback_data": f"order_{offer.offer_id}_1"},
                        {"text": self._t("order_2"), "callback_data": f"order_{offer.offer_id}_2"},
                    ]
                ]
            }
        return text, reply_markup

    @staticmethod
    def _state(offer, cancelled: bool):
        """Return (icon, suffix_translation_key, is_active)."""
        if cancelled:
            return _CANCELLED_ICON, "status_cancelled", False
        if offer.status == OfferStatus.SOLD_OUT.value:
            return _SOLD_OUT_ICON, "status_sold_out", False
        return "", "", True
