from typing import Any

from models.entities import OfferStatus
from services import offer_listing, offer_overview

from .base import OfferBaseHandler

# Telegram allows 4096 characters per message; leave room for the "TEST - " prefix
MESSAGE_LIMIT = 4000


class OfferOverviewHandler(OfferBaseHandler):
    """/offer_overview: the offers that can be ordered, for the admin to edit and pin in the group"""

    def handle_offer_overview(self, chat_id: int) -> dict[str, Any]:
        """The active offers grouped by the style in their name (services/offer_overview.py), each line with a link
        to the offer and what is left of it. Sent to the admin only, in Dutch like every text for the group; split
        over messages between lines when it is long."""
        offers = [offer for offer in self.db.list_offers() if offer.status == OfferStatus.ACTIVE.value]
        if not offers:
            self._send_message(chat_id, self._t("offer_overview_empty", chat_id))
            return {"status": "no_offers"}

        boxes = offer_listing.by_offer(self.db.get_all_boxes())
        bot_username = self._get_bot_username()
        blocks = [f"<b>{self._group_text('offer_overview_title')}</b>"]
        for key, group in offer_overview.grouped(offers):
            lines = [self._offer_line(offer, boxes.get(offer.offer_id, []), bot_username) for offer in group]
            blocks.append(f"<b>{self._group_text(f'offer_overview_group_{key}')}</b>\n\n" + "\n".join(lines))

        for message in self._messages(blocks):
            self._send_message(chat_id, message, parse_mode="HTML")
        return {"status": "success"}

    def _group_text(self, key: str, **params) -> str:
        return self._t(key, force_group_lang=True, **params)

    def _offer_line(self, offer, boxes: list, bot_username: str) -> str:
        """🍺, the offer number (bold, a link to the offer), the name (bold), the price, and how many can still be
        ordered when that is limited"""
        link = f"<a href='https://t.me/{bot_username}?start=view_offer_{offer.offer_id}'><b>{offer.offer_id}</b></a>"
        line = f"🍺 {link} <b>{self._escape_html(offer.name)}</b> €{offer.price_per_unit:.2f}"
        left = offer_overview.can_still_be_ordered(boxes)
        return f"{line} ({left})" if left else line

    @staticmethod
    def _messages(blocks: list[str]) -> list[str]:
        """The blocks (title, groups) joined by a blank line, in messages that fit, split between lines"""
        messages: list[str] = []
        current = ""
        for line in "\n\n".join(blocks).split("\n"):
            if current and len(current) + 1 + len(line) > MESSAGE_LIMIT:
                messages.append(current.rstrip("\n"))
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            messages.append(current)
        return messages
