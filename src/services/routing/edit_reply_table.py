"""The table of prompt answers: which handler method gets the text the admin types after a prompt.

A prompt stores an edit context (``utils/edit_context.py``) with a type. The next message the admin sends in their
private chat is the answer, and its type decides where it goes. A new prompt type is a new line here; reading and
checking the answer (a number, a price) is the handler's job.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PromptAnswer:
    """The admin's answer to an open prompt"""

    chat_id: int
    user_id: int
    text: str
    entity_id: str  # what the prompt is about (an offer id, an order id, ...), as stored with the edit context
    message: dict[str, Any] = field(default_factory=dict)  # the whole Telegram message


ArgumentBuilder = Callable[[PromptAnswer], tuple[Any, ...]]


@dataclass(frozen=True)
class AnswerRoute:
    handler: str  # key in the handlers dict
    method: str
    arguments: ArgumentBuilder
    users_menu_when_not_found: bool = False  # an unknown user: back to the admin users menu


# --- argument builders: (chat, ...) as the handler method expects them -----------------------------------


def entity_and_text_as_args(a: PromptAnswer) -> tuple:
    return (a.chat_id, [a.entity_id, a.text])


def text(a: PromptAnswer) -> tuple:
    return (a.chat_id, a.text)


def text_as_args(a: PromptAnswer) -> tuple:
    return (a.chat_id, [a.text])


def user_text_as_args(a: PromptAnswer) -> tuple:
    return (a.chat_id, a.user_id, [a.text])


def words(a: PromptAnswer) -> tuple:
    return (a.chat_id, (a.text or "").split())


def entity_then_text(a: PromptAnswer) -> tuple:
    return (a.chat_id, a.entity_id, a.text)


def text_then_entity(a: PromptAnswer) -> tuple:
    return (a.chat_id, a.text, a.entity_id)


def description(a: PromptAnswer) -> tuple:
    """The formatting (bold, italic) of a description comes with the message as entities"""
    return (a.chat_id, a.entity_id, a.text, a.message.get("entities") or [])


def incomplete_delivery(a: PromptAnswer) -> tuple:
    return (a.chat_id, a.user_id, a.text, a.entity_id)


def cancel_reason(a: PromptAnswer) -> tuple:
    return (a.chat_id, a.entity_id, (a.text or "").strip() or "No reason provided")


# --- the table ---------------------------------------------------------------------------------------------

ANSWER_ROUTES: dict[str, AnswerRoute] = {
    # Suppliers
    "create_supplier_name": AnswerRoute("supplier", "create_supplier", text),
    "supplier_name": AnswerRoute("supplier", "handle_update_supplier_name", entity_and_text_as_args),
    "supplier_contact": AnswerRoute("supplier", "handle_update_supplier_contact", entity_and_text_as_args),
    "supplier_full_name": AnswerRoute("supplier", "handle_update_supplier_full_name", entity_and_text_as_args),
    # Offers
    "offer_name": AnswerRoute("offer", "handle_update_offer_name", entity_and_text_as_args),
    "offer_price": AnswerRoute("offer", "handle_update_offer_price", entity_and_text_as_args),
    "offer_description": AnswerRoute("offer", "handle_offer_description_answer", description),
    "custom_wholesale_quantity": AnswerRoute("offer", "handle_custom_wholesale_quantity_answer", entity_then_text),
    # Users
    "customer_first_name": AnswerRoute("user", "handle_update_user_first_name", entity_and_text_as_args),
    "customer_last_name": AnswerRoute("user", "handle_update_user_last_name", entity_and_text_as_args),
    "customer_contact": AnswerRoute("user", "handle_update_user_contact", entity_and_text_as_args),
    "customer_location": AnswerRoute("user", "handle_update_user_location", entity_and_text_as_args),
    "approve_user_input": AnswerRoute("user", "handle_approve_user", text_as_args, users_menu_when_not_found=True),
    "user_status_input": AnswerRoute("user", "handle_user_status", text_as_args, users_menu_when_not_found=True),
    # Orders
    "list_user_orders_input": AnswerRoute("admin_order", "handle_list_user_orders", text_as_args),
    "cancel_order_input": AnswerRoute("admin_order", "handle_cancel_order", text_as_args),
    "cancel_order_reason": AnswerRoute("admin_order", "handle_confirm_cancel_with_reason", cancel_reason),
    "order_for_input": AnswerRoute("admin_order", "handle_create_order_for", user_text_as_args),
    "order_for_quantity_input": AnswerRoute("admin_order", "handle_create_order_for_quantity_answer", entity_then_text),
    "edit_order_price_input": AnswerRoute("admin_order", "handle_edit_order_price_answer", entity_then_text),
    # Deliveries, payments and reports
    "incomplete_delivery": AnswerRoute("wholesale_delivery", "handle_incomplete_delivery_reply", incomplete_delivery),
    "payment_link_input": AnswerRoute("delivery_overview", "handle_payment_link_input", text_then_entity),
    "report_customer_input": AnswerRoute("report", "handle_report_customer", words),
}
