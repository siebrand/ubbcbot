# Code quality audit 4: where stock and money change

Status: **open** (2026-11-19). Follows audit 3 (what the bot sends), which is done. The first three audits went
through the largest files and the messages; this one follows the code that changes what a customer owes or gets:
credits, the wholesale delivery and labeling workflows, the CSV import, and the per-container caches and test
safeguards around them. Same priorities as before:

- **High**: wrong behaviour, a security or privacy risk, money that comes out wrong.
- **Medium**: a structural problem with a clear payoff (non-atomic writes, duplication, text that bypasses the
  translations).

Every fix comes with a test that fails before it. Code that touches capacity or credit uses DynamoDB conditions or
transactions (CLAUDE.md, Gotchas).

## Scope

| Area                         | Files                                                                                           |
|------------------------------|-------------------------------------------------------------------------------------------------|
| Credits                      | `src/services/credit_service.py`, `src/repositories/credit_repository.py`, `src/handlers/admin/credit_commands.py` |
| Wholesale delivery, labeling | `src/services/wholesaler_delivery.py`, `src/handlers/admin/wholesale_delivery_handler.py`, `src/handlers/admin/labeling_completion_handler.py`, `src/handlers/admin/delivery_overview_handler.py` |
| CSV import                   | `src/handlers/admin/import_handler.py`, `src/utils/validation.py` (`match_customers`, `load_customers`) |
| Caches and shared utilities  | `src/services/user_cache.py`, `src/utils/pagination.py`                                         |
| The message Lambda           | `src/message_sender.py` (`lambda_handler`)                                                      |
| Test safeguards              | `tests/conftest.py`                                                                             |

## High priority

- [x] **A1. A partly cancelled wholesale delivery is never charged, and the customer is told it is coming**
  (`wholesaler_delivery.py`, `_process_partial_cancelled`). When fewer units arrive and the rest is cancelled, the
  order that is partly filled keeps its full `quantity` and `total_price`, gets `received_quantity` < `quantity` and
  goes to `ready_for_labeling`; a separate cancelled order is written for the missing units. The delivery overview
  (`delivery_overview_handler.py`, `start_send_overviews`) treats every order with `received_quantity < quantity` as
  delayed: the payment message lists the cancelled units under "will arrive later" and leaves the received units out
  of the amount to pay. Fix: reduce the filled order to the received units (`quantity`, `total_price`), so it is
  delivered and charged; keep the cancelled remainder as its own order. Test: a box of 6 ordered, 4 arrive, rest
  cancelled → the overview charges 4 units and mentions nothing as delayed. **Done**: the partly filled order now
  gets `quantity` and `total_price` of the received units; the cancelled remainder stays its own order.
  `tests/test_wholesale_partial_delivery.py` runs delivery, labeling and the overview against moto. Orders cut off
  entirely, and the delayed path, were already right.
- [ ] **A2. The CSV import creates orders for customers who are not approved** (`import_handler.py`,
  `handle_document_upload`). It matches the names against `validator.load_customers()`, which returns approved,
  unauthorized and rejected customers alike, and writes the order directly, past `handle_create_order`, which is
  where approval is enforced (CLAUDE.md: "for every entry point"). The orders of a rejected customer are then never
  in a delivery overview (that only reads approved customers). Fix: load only approved customers; a line whose name
  only fits a customer who is not approved is an error line ("not approved"). Test: a file with a rejected customer's
  name imports nothing for that line.
- [ ] **A3. `/credit` without a reason always fails, and a malformed amount raises** (`credit_commands.py`,
  `credit_service.py`). The usage says `/credit <username> <amount> [reason]`, but `issue_credit` refuses an empty
  reason, so `/credit jan 5` answers "Failed to issue credit". `Decimal("abc")` raises `decimal.InvalidOperation`,
  which is not the `ValueError` the handler catches, so `/credit jan abc` ends in the generic error. `NaN` gets past
  the parse and raises on `amount < 0`; `Infinity` and `1e9` are accepted. Fix: make the reason optional for a
  positive amount (as the usage says) or required for every amount (and say so); parse the amount as a finite
  number with at most two decimals and a sane upper bound. Tests for each input.
- [ ] **A4. The payment-received message puts the pickup location into HTML unescaped**
  (`delivery_overview_handler.py`, `handle_process_customer_paid`: `payment_received_notification` is sent with
  `parse_mode="HTML"` and `location=customer.location`). The location is typed by the admin; a "<" in it makes
  Telegram refuse the message, so the customer never hears that the payment arrived (the delivery message escapes the
  same field since audit 2). Fix: `_escape_html(customer.location)`. Test: a location with `<` and `&`.
- [ ] **A5. A rejection or approval is not seen by other warm containers** (`user_cache.py`). The cache of customers
  (by status and by Telegram id) lives per Lambda container without an expiry. Approving or rejecting a user
  invalidates it only in the container that handled the command; another warm container keeps the old status and
  goes on letting a rejected user order (or refusing an approved one) until it is recycled. Fix: a short time to live
  (a minute), or read the authorization status of the sender from the table on every update (one `GetItem`) and keep
  the cache only for lists. Test: two `BotService` instances share the table; a rejection through one is refused by
  the other.

## Medium priority

- [ ] **B1. The credit balance and its transaction are two writes, and the applied credit can wipe a concurrent
  one** (`credit_service.py`). `issue_credit` writes the transaction and then the balance; if the second write fails,
  the history shows a credit the balance does not have. `_update_customer_credit_balance` turns the intended new
  balance into a delta against a second read of the balance: when an admin issues credit between the two reads in
  `apply_credit_to_delivery`, the delta also removes that new credit. Fix: compute the delta once from the balance
  that was used, and write the transaction and the `ADD` in one `TransactWriteItems` (with a condition on the balance
  that was read). Test: a credit issued between the read and the write survives.
- [ ] **B2. The customers are never told about a delayed or cancelled wholesale delivery**
  (`wholesaler_delivery.py`, `notify_customer_of_delay` and `notify_customer_of_cancellation` only log "STUB").
  Fix: tell them through `_notify_customer` (translated, guests skipped), or remove the stubs and say in the delivery
  messages what happened. Decide with the owner which; the delivery overview already mentions delayed units.
- [ ] **B3. An imported order and its box are two writes** (`import_handler.py`, `_create_import_order`): the order
  is written with `create_order` and the box incremented afterwards, so an import that runs while customers order
  can overfill a box or leave an order without its unit in the box. Fix: `create_order_with_box_increment` (the
  transaction customers' orders use), and try the next box when it is rejected.
- [ ] **B4. Finalizing an import offer without boxes announces it but leaves it in `import`**
  (`import_handler.py`, `handle_finalize_import`). `update_offer_status_after_change` returns None when the offer has
  no boxes; the handler then sets `offer.status = ACTIVE` on the object only, announces it, and the table still says
  `import`. Fix: write the status, or refuse to finalize an offer without imported orders.
- [ ] **B5. The CSV import picks a customer by substring** (`validation.py`, `match_customers`, used by the
  import). "Bert" matches "Robert" when there is only one of them; the ambiguity check (audit 2) only catches names
  that match several customers. For an import, which has nobody to ask, match the full name or username exactly
  (case-insensitive), or a customer id; keep the substring search for the interactive commands.
- [ ] **B6. A completed offer keeps its order buttons after labeling** (`labeling_completion_handler.py`,
  `_check_and_update_offer_status`). It sets the offer to `completed` but does not sync the announcements, unlike
  `BaseHandler._check_offer_status_after_change`. Fix: `sync_offer_messages` after the status change. Test: the last
  box labeled syncs the messages once.
- [ ] **B7. The labeling and credit screens bypass the admin's language** (`labeling_completion_handler.py`: every
  `_t` without the user; `credit_commands.py`: "No reason provided", the credit notification through
  `_send_message(customer.telegram_user_id, ...)` instead of `_notify_customer`; `test_commands.py`: "✓ Test message
  sent", "✗ Failed to send message"; `import_handler.py`: "({n} orders)"). Fix: translate with the reader, and
  message customers through `_notify_customer`.
- [ ] **B8. The plain page buttons are English** (`utils/pagination.py`, `build_pagination_keyboard` without
  `enhanced`: "◀️ Previous", "Page x/y", "Next ▶️"; found in audit 3, B3). Used by the supplier list and
  `/changelog`. Fix: let the caller pass the translated labels, or use the enhanced (icon-only) buttons everywhere.
- [ ] **B9. The message Lambda returns the text of an exception** (`message_sender.py`, `lambda_handler`: the body
  holds `str(e)` and the log the full message). An SSM or Telethon error can name the parameter, the session or a
  user; the webhook and callback paths return only the exception type since audit 2. Fix: the type only, in both.
- [ ] **B10. A test can reach the real Telegram API** (`tests/conftest.py`). In audit 3 (B4) a test sent a real
  request because a second handler's `_send_message` was not mocked; nothing stops that. Fix: an autouse fixture that
  makes `requests` (and `boto3` outside moto) fail loudly in tests, so a missed mock is a failure, not a request.

## Order of work

The money first, each with a test that fails before the fix: A1, A3, then A2 (import approval), A4, A5. Then the
writes that must be atomic: B1, B3. Then B10 (so the rest cannot reach the network), B4, B5, B6, B9, and last the
texts: B7, B8. B2 needs a decision from the owner first: ask before building it.
