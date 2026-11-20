# Code quality audit 5: where the money is collected

Status: **open** (2026-11-20). Follows audit 4 (where stock and money change), which is done. Audit 4 followed the
writes that change what a customer owes or gets; this one follows what happens next: the delivery overview with its
payment link, marking a payment as received, the reminders, credit at payment time, and the follow-ups audit 4 left.
Same priorities as before:

- **High**: wrong behaviour, a security or privacy risk, money that comes out wrong.
- **Medium**: a structural problem with a clear payoff (non-atomic writes, duplication, text that bypasses the
  translations).

Every fix comes with a test that fails before it; every refactor with a test that pins the behaviour first. Code that
touches capacity or credit uses DynamoDB conditions or transactions (CLAUDE.md, Gotchas). The customer-name matching
is fuzzy on purpose, also in the CSV import (owner, 2026-11-20): do not make it exact.

## Scope

| Area                         | Files                                                                                             |
|------------------------------|---------------------------------------------------------------------------------------------------|
| Delivery overview            | `src/handlers/admin/delivery_overview_handler.py`, `src/handlers/payment_message.py`              |
| Payments and reminders       | `src/handlers/admin/order/order_status.py` (`/process_payment`, `/send_payment_reminder`, `/failed_notifications`, `/send_delivery_overviews`) |
| Delayed wholesale units      | `src/services/wholesaler_delivery.py` (`_process_partial_delayed`), the status `received_partial_delayed` |
| Credit at payment time       | `src/services/credit_service.py` (`apply_credit_to_delivery`)                                     |
| Writes on the way            | `src/repositories/order_repository.py` (`batch_update_order_status`), `src/repositories/system_repository.py` (payment link) |
| The message Lambda           | `src/message_sender.py` (`send_from_admin`)                                                        |

## High priority

- [x] **A1. Orders whose units are delayed are stranded** (`wholesaler_delivery.py`, `_process_partial_delayed`).
  When fewer units arrive and the rest is delayed, the orders that are not (fully) filled get the status
  `received_partial_delayed` and the box is marked `delivered`. Nothing reads that status again (only an emoji in
  the order list): the units that did arrive are never labeled or charged, and the delivery flow only offers
  `ordered` boxes, so the late units can never be booked in. Fix: as for a cancelled rest (audit 4, A1), split the
  received units of a partly filled order into an order of their own that goes to labeling; the delayed units stay an
  `ordered` order, and the box stays `ordered` while it has them, so the next `/process_delivery` finds it. Test: 6
  ordered, 4 arrive, the rest delayed → 4 are labeled and charged; delivering the other 2 later charges them too.
  **Done**: an order the delivery does not reach stays `ordered`; a partly filled one is split by the new
  `OrderRepository.split` (`DynamoDBService.split_order`): one transaction that shrinks the order to the received
  units (ready for labeling) and writes the rest as an order of its own, on condition that the order still has the
  status and quantity it was read with. The box is only marked delivered when none of its orders is `ordered`. The
  cancelled rest of audit 4, A1 now goes through the same split (it was two writes). Nothing sets
  `received_partial_delayed` any more. Not done here: orders that already have that status in the table stay
  stranded; check prod for them (a one-off script can split them the same way). When a split is refused, the order
  stays `ordered` whole and nobody is told (logged). `TestRestDelayed` in `tests/test_wholesale_partial_delivery.py`.
- [ ] **A2. Credit is never applied to a payment** (`credit_service.py`, found in audit 4, B1).
  `apply_credit_to_delivery` has no caller: a customer with credit pays the full amount, and a debt (a negative
  balance from `/credit`) is never charged. The payment message does not mention credit either. Fix: apply the
  balance once, when the overview moves the orders to `awaiting_payment`, show it in the payment message ("credit
  used", "still to pay"), and keep what was applied with the orders, so a reminder shows the same amount and does not
  apply it again. Test: 5 credit, an overview of 12 asks for 7 and the balance is 0; the reminder asks for 7 too.
- [x] **A3. The payment link goes into the HTML message unescaped, and anything is accepted as a link**
  (`payment_message.py`, `pay_via_payment_request` with `link=payment_link`; `handle_payment_link_input`). The link is
  typed by the admin; a `&` or `<` in it breaks the message (Telegram refuses it, so no customer of the batch gets an
  overview while their orders still move on, see A4). Fix: accept only an `https://` URL without spaces, escape it
  in the message. Tests for both. **Done**: `PAYMENT_LINK_PATTERN` (https, no spaces, at most 2000 characters);
  anything else gets `invalid_payment_link` and the same batch is asked for again, before anything is stored, moved or
  sent. The link is escaped in the payment message, so also in reminders (same builder).
  `TestThePaymentLink` in `tests/test_overview_payment_link.py`.
- [x] **A4. Orders move to `awaiting_payment` whatever happens to them in between** (`handle_payment_link_input`,
  `batch_update_order_status`). The order ids are collected when the overview starts and stored in the edit context;
  when the admin replies with the link, every one of them is set to `awaiting_payment` without a condition. An order
  cancelled (or paid, or moved) in between is set back to `awaiting_payment` and charged. Fix: the update only from
  `labeling_completed` (`ConditionExpression`), and the message only lists the orders that moved. Test: an order
  cancelled between the start and the link is neither charged nor listed. **Done**: `batch_update_order_status`
  takes a `from_status` (a condition per order) and returns the ids it moved, not a count; a payment event is only
  recorded for an order that moved. The overview now moves the orders first and builds each message from the ones
  that moved; a customer left with nothing gets no message (and the sender is not invoked for an empty batch). Found
  along the way: a paid order was set back to `awaiting_payment` the same way. `tests/test_overview_payment_link.py`.
- [x] **A5. "Payment received" names an amount that was not all marked paid** (`delivery_overview_handler.py`,
  `handle_process_customer_paid`). `total_amount` adds up every order awaiting payment, also the ones
  `mark_order_paid` failed for, and the customer is told that amount was received. Fix: the total of the orders that
  were marked; when some failed, tell the admin which. Test: two orders, one fails → the customer hears the amount of
  one, the admin hears of the failure. **Done**: the total (for the customer and the admin) is that of the orders
  that were marked; when only some were, the admin gets `payment_partly_marked` (the others still await payment).
  `tests/test_payment_received_notification.py`.

## Medium priority

- [ ] **B1. `/failed_notifications` lists overviews that were never sent, not ones that failed**
  (`order_status.py`, `handle_failed_notifications`). It shows customers with `labeling_completed` orders; a failed
  overview has already moved its orders to `awaiting_payment` (the send is asynchronous), so it is never listed. The
  message sender does tell the admin which messages failed. Fix: rename and reword it as "not yet sent", or keep the
  failures (the sender knows them) and list those. Decide which; the text says "need to be contacted manually".
- [ ] **B2. The reminder uses the last payment link, whatever batch the customer was in**
  (`handle_send_payment_reminder_to_customer`, `system_repository.py`: one `payment_link` item). The overview asks for
  a link per batch of 50; a reminder to a customer of the first batch carries the link of the last. Fix: keep the link
  with the orders (or per batch) and remind with the customer's own; or, if one link fits everyone, ask for it once.
- [ ] **B3. Four copies of "approved customers with orders in status X", each with a query per customer**
  (`order_status.py` three times, `start_send_overviews`). Every screen reads all approved customers and then the
  orders of each, one query per customer. Fix: one helper that reads the orders by status (`status-index` exists) and
  groups them by customer; pin the four screens first.
- [ ] **B4. Text that bypasses the translations or the reader's language** (found in audit 4, B7). English in the
  code: the `/send_delivery_overviews` summary, `/failed_notifications` ("orders", "no_username", the closing hint),
  "📧 Ready for next batch...", "Total:" in the admin copy of an overview. And many handlers call `_t` without a
  reader, so the admin always gets Dutch: the import screens, `_validate_args`, `_send_error`/`_send_success` without
  `user_id`, most of `delivery_overview_handler.py` and `order_status.py` (`user_id=None`). Fix: translate with the
  reader (admin screens: the admin); a test that walks the admin screens in English.
- [ ] **B5. The admin sees the text of an exception** (`error_processing_payment_link` with `error=str(e)`,
  `_send_user_message` returns `str(e)`, `send_from_admin` in `message_sender.py` reports and logs the text of a
  Telethon error; audit 4, B9). Fix: the type only, except the Telethon messages the failure report needs ("Could not
  find the input entity" is already mapped; map a flood wait the same way).

## Order of work

The money first, each with a test that fails before the fix: A4 (the unconditional update), A5, A3, then A1 (the
delayed units) and A2 (credit, which builds on the overview). Then B3 (one helper, with the four screens pinned
first), B2, B1, B5, and last the texts: B4. B1 and B2 have two possible fixes: pick one and say why in the note.
