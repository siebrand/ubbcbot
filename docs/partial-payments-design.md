# Partial Payments: Technical Design

Status: implemented (2026-11-21). The use cases are in
[instant-orders-and-partial-payments.md](instant-orders-and-partial-payments.md). This document says how to build
them, in small steps that each leave the bot working and the tests green.

## 1. What the current system does

| Subject | Today |
|---|---|
| Payment list | `/process_payment` (`OrderStatusManagement.handle_process_payment`) lists approved customers that have `awaiting_payment` orders. One button per customer: `process_payment_<customer_id>_<page>`. |
| Paying | Tapping that button runs `DeliveryOverviewHandler.handle_process_customer_paid`. It marks all open orders of the customer as `completed`, one `mark_order_paid` per order. It then tells the admin and the customer, and shows the list again. |
| Payment event | `DynamoDBService.update_order` and `batch_update_order_status` write one `PAYMENT_RECEIVED` event when an order goes from `awaiting_payment` to `completed`. The event amount is `order.total_price`. |
| Amount due | `Order.amount_due = total_price - credit_applied`. The delivery overview sets `credit_applied`. It is the amount the customer sees in the overview and in reminders. |
| One order paid | `/edit_order` can already set one `awaiting_payment` order to `completed` (`OrderEditing._status_options`). It stays as it is. |
| Reminders | `/send_payment_reminder` and `/payment_info` build their text from the `awaiting_payment` orders only. After a partial payment they show only what is left. UC2.5 needs no change. |
| Order age | `update_date` is set when the delivery overview moves the order to `awaiting_payment`. The credit write does not change it. |
| Prompts | The admin's typed answers go through `ANSWER_ROUTES` (`services/routing/edit_reply_table.py`). The context is deleted before the handler runs, so a handler that wants another answer stores a new context. |
| Buttons | Callback data is limited to 64 bytes. |

No new table, index, Lambda, environment variable or IAM change is needed. `get_approved_customers_with_orders`
already reads the open orders with one query on the `status-index`.

## 2. Decisions

- **Whole orders only.** A payment settles a set of whole orders. This matches how `PAYMENT_RECEIVED` events work, so
  the reports do not change (UC2.7).
- **Matching uses `amount_due`**, the amount the customer was asked to pay. The `PAYMENT_RECEIVED` event keeps the
  amount it has today, `total_price`. For an order with credit applied, the reports therefore count the price before
  credit, as they do today for "pay everything". This design does not change that.
- **"Oldest" means the order that has been open the longest:** sorted by `update_date` (when it became
  `awaiting_payment`), then `created_at`, then `order_id`.
- **Search for the exact set** with a bitset over cents (section 3). The result is the set that contains the oldest
  order, then the next oldest, and so on. This is the set the use case asks for (UC2.3).
- **Stateless confirmation.** The proposal is not stored. The confirm button carries the customer ID, the amount in cents
  and a short hash of the selected order IDs. On confirm, the bot searches again and refuses when the hash differs. This
  covers orders that changed in between and a second tap on the same button.
- **One more button per row, not a menu.** Each row of the `/process_payment` list gets a second button next to the
  existing one, so "pay everything" stays one tap.

## 3. Behavior details

**Amount input.** The admin types a number: `40`, `40.5`, `40,50` or `€40.50`. It must be greater than 0, have at most
two decimals and be at most 10 000. Anything else gets `payment_amount_invalid`, and the prompt is asked again.

**Search** (`services/payment_matching.py`, pure functions):

1. `open_orders` are the customer's `awaiting_payment` orders, read fresh from the database.
2. `settle_with` are the orders with `amount_due <= 0`. They are not part of the search.
3. `payable` are the rest, sorted oldest first. Amounts are converted to cents with `ROUND_HALF_UP`.
4. If there are more than 60 payable orders, or their total is above 10 000 000 cents, the result is `too_many`. The admin
   is told, and nothing is registered.
5. `suffix[i]` is an integer used as a bitset: bit `s` is set when the sum `s` can be made from `payable[i:]`.
   `suffix[n] = 1` and `suffix[i] = suffix[i+1] | (suffix[i+1] << cents[i])`.
6. If bit `target` of `suffix[0]` is set, rebuild the set oldest first: for each order, take it when `target - cents[i]`
   is reachable from `suffix[i+1]`, otherwise skip it.
7. If not, the closest total is the nearest set bit to `target` among the non-empty sets. The lower total wins a tie.

**Proposal message.** Customer name, the amount, the selected orders (offer, date, amount due), the zero-due orders that
will be settled with it (amount 0.00), and what stays open (total and number of orders). Buttons: confirm
(`payok_<customer_id>_<cents>_<token>_<page>`, 61 bytes at most) and cancel.

**Confirm.** Search again for the same cents. When the token of the new selection differs, send `payment_match_changed`
and show the list again. Otherwise run
`db.batch_update_order_status(ids, COMPLETED, admin_id, from_status=AWAITING_PAYMENT)` for the selected orders and the
zero-due orders. It sets each order only while it is still `awaiting_payment` and writes the `PAYMENT_RECEIVED` events for
those it changed. The orders it could not change are reported with the existing `payment_partly_marked` message. The admin
gets the existing `payment_confirmed` message. The list is shown again.

**Customer message.** From the admin account, as the current payment message is, and not for guests.

- Orders remain open: the new `payment_partial_received_notification` (amount received, number of orders, what is still
  to pay).
- Nothing remains open: the existing `payment_received_notification`.

**`/list_open_payments`.** Read only. One line per customer with open orders: name, open total (`amount_due`), number of
orders, and the age in days of the oldest open order. Oldest first, 10 per page, with a button to `/process_payment`.

## 4. Atomic changes

Each change is one commit. Run `scripts/static-analysis.sh` and the full test suite after each.

### PP-1. Amount parsing and exact matching

- **Files:** `src/services/payment_matching.py` (new), `tests/test_payment_matching.py` (new).
- **Change:** pure functions, no database and no Telegram.

```python
MAX_PAYMENT_AMOUNT = Decimal("10000")
MAX_MATCH_ORDERS = 60
MAX_MATCH_CENTS = 10_000_000


@dataclass(frozen=True)
class PaymentMatch:
    selected: list[Order]  # oldest first, amounts due add up to the target
    settle_with: list[Order]  # zero-due orders, settled together with it


@dataclass(frozen=True)
class MatchResult:
    match: PaymentMatch | None
    closest_total: Decimal | None  # when there is no match
    too_many: bool = False


def parse_amount(text: str) -> Decimal | None: ...
def age_key(order: Order) -> tuple: ...
def find_payment_match(open_orders: list[Order], amount: Decimal) -> MatchResult: ...
def selection_token(orders: list[Order]) -> str: ...  # first 6 hex characters of the sha1 of the sorted order IDs
```

- **Tests:**
  - `parse_amount`: valid forms; `0`, negative, `abc`, three decimals, above 10 000, empty.
  - Matching: exact single order; exact set of several; the set that contains the oldest order when several sets match;
    no match returns the closest total (lower wins a tie); zero-due orders go to `settle_with` and never change the
    sum; amounts that are not whole euros; a debt (`credit_applied < 0`); an empty list; more than 60 orders gives
    `too_many`; a total above the cent limit gives `too_many`.
  - A brute-force comparison with `itertools.combinations` on random lists of up to 10 orders: same yes or no for every
    target, and the same set.
  - `selection_token` does not depend on the order of the list.
- **Commit:** `feat: match a payment amount to the oldest open orders`

### PP-2. Proposal and confirmation (not yet reachable)

- **Depends on:** PP-1.
- **Files:** `src/handlers/admin/order/order_status.py`, `src/handlers/admin/order_commands.py`, `src/translations/en.json`,
  `nl.json`, `tests/test_partial_payment.py` (new).
- **Change:** in `OrderStatusManagement`:
  - `handle_payment_amount_answer(chat_id, entity_id, text)`: `entity_id` is `<customer_id>_<page>`. Parse the amount
    (invalid: error and store the same context again). Read the customer and the open orders. Search. Send the proposal,
    or `payment_match_none` (amount and closest total) and the list again, or `payment_match_too_many` and the list again.
  - `handle_payment_confirm(chat_id, customer_id, cents, token, page)`: as in section 3, without the customer message
    (PP-3).
  - `AdminOrderCommands` delegates both methods.
- **New keys:** `payment_amount_invalid`, `payment_match_proposal`, `payment_match_none`, `payment_match_too_many`,
  `payment_match_changed`, `payment_match_confirm_btn`.
- **Tests (moto):**
  - A match shows a proposal with the right orders and a confirm button whose data is at most 64 bytes.
  - Confirm marks exactly the selected and the zero-due orders as `completed`, leaves the others `awaiting_payment`, and
    writes one `PAYMENT_RECEIVED` event per marked order with `total_price` as the amount.
  - No match: nothing changes, the closest total is reported and the list is shown.
  - Orders changed after the proposal (one cancelled, one paid by hand): the token differs, nothing changes.
  - A second confirm after success changes nothing.
  - One order that fails the conditional update is reported with `payment_partly_marked`, and the others are marked.
  - A customer that is not found, or has no open orders, gets the existing messages.
- **Commit:** `feat: register a partial payment for the oldest matching open orders`

### PP-3. Message to the customer

- **Depends on:** PP-2.
- **Files:** `src/handlers/admin/order/order_status.py`, `src/translations/en.json`, `nl.json`,
  `tests/test_partial_payment.py`.
- **Change:** after a confirmed payment, send the customer message of section 3 with `_send_user_message`, in the
  customer's language. Skip guests. A failed send does not undo the payment. The admin sees a line that the customer was
  not reached.
- **New key:** `payment_partial_received_notification`.
- **Tests:** a partial payment sends the new message with the paid amount and the open amount. The last payment sends the
  existing message. A guest gets nothing. A failed send is reported and the orders stay paid. The language follows the
  customer.
- **Commit:** `feat: tell the customer about a partial payment`

### PP-4. Make it available from `/process_payment`

- **Depends on:** PP-2, PP-3.
- **Files:** `src/handlers/admin/order/order_status.py`, `src/services/callback_handler.py`,
  `src/services/routing/edit_reply_table.py`, `src/utils/edit_context.py`, `src/translations/en.json`, `nl.json`,
  `tests/test_mark_paid_pagination.py`, `tests/test_admin_payment_screens_in_english.py`,
  `tests/test_callback_routing.py`, `tests/test_prompt_answers.py`.
- **Change:**
  - `handle_process_payment`: each row gets a second button `payment_amount_btn` ("💶") with callback
    `payment_amount_<customer_id>_<page>`. The first button is unchanged.
  - Callback `^payment_amount_([^_]+)_(\d+)$`: store an edit context (`payment_amount_input`, entity `<customer_id>_<page>`)
    and send the prompt with force reply. Admin only, keyboard removed.
  - `ANSWER_ROUTES["payment_amount_input"] = AnswerRoute("admin_order", "handle_payment_amount_answer", entity_then_text)`.
  - Callback `^payok_([^_]+)_(\d+)_([0-9a-f]{6})_(\d+)$` runs `handle_payment_confirm`. Admin only, message deleted.
  - Prompt keys: `enter_payment_amount`, `placeholder_payment_amount`, `payment_amount_btn`.
- **Tests:** the rows have two buttons and the first one still pays everything. The prompt is stored and answered. A
  customer who taps `payment_amount_` or `payok_` is refused. The worst-case callback data is at most 64 bytes. The flow
  from the list to a confirmed payment works end to end.
- **Commit:** `feat: add the amount received button to /process_payment`

### PP-5. `/list_open_payments`

- **Depends on:** none. Ship after PP-4 so the button in it leads to a complete flow.
- **Files:** `src/handlers/admin/order/order_status.py`, `src/handlers/admin/order_commands.py`,
  `src/services/routing/command_table.py`, `src/services/callback_handler.py`, `src/handlers/admin/admin_commands.py`,
  `telegram-commands.json`, `src/translations/en.json`, `nl.json`, `tests/test_open_payments.py` (new),
  `tests/test_command_routing.py`.
- **Change:**
  - `OrderStatusManagement.handle_list_open_payments(chat_id, args, page=1)`: read the open orders, group by customer,
    sort by the oldest `age_key`, paginate with `PaginationUtils` (10 per page), show the lines of section 3 and a button
    to `/process_payment` and a back button.
  - Command `"/list_open_payments": admin_command("admin_order", "handle_list_open_payments", private_rest)`.
  - Page callback `^page_list_open_payments_(\d+)$` and panel callback `cmd:list_open_payments`.
  - `handle_admin_orders` gets a button `list_open_payments_btn`.
  - `telegram-commands.json`: admin entry `list_open_payments`, alphabetical, "Customers with unpaid orders and their age".
  - New keys: `list_open_payments_title`, `list_open_payments_line`, `no_open_payments`, `list_open_payments_btn`,
    `open_payments_process_btn`.
- **Tests:** customers with open orders are listed, oldest first, with the right totals (`amount_due`), counts and ages.
  Customers without open orders are not listed. Paging. A non-admin gets no answer. The menu test passes.
- **Commit:** `feat: add /list_open_payments`

### PP-6. Documentation and changelog

- **Depends on:** PP-5.
- **Files:** `README.md`, `src/translations/en.json`, `nl.json` (`help_delivery`),
  `src/handlers/customer/changelog_commands.py`, `docs/instant-orders-and-partial-payments.md`.
- **Change:** README: the `/list_open_payments` command and the amount button in the `/process_payment` line, plus a
  "Partial payments" section under Features (whole orders, exact match, oldest first, no credit involved). `help_delivery`
  lists `/list_open_payments`. One changelog bullet in the admin-facing part and one in the user-facing part (the new
  message). `tests/test_changelog.py` checks page length and HTML balance. Set the use case document to "implemented".
- **Commit:** `docs: describe partial payments`

## 5. Deployment

- No data migration and no template change.
- Deploy with `./deploy.sh test`, check, then `./deploy.sh prod`. The script runs `setup-commands.sh`, which adds
  `/list_open_payments` to the admin menu.
- Check in the test environment with one customer that has three open orders (for example 12.00, 8.50 and 20.00):
  enter 20.50 (first two, oldest first), enter 5.00 (no match, closest total shown), then pay the rest with the
  existing button.

## 6. Risks and limits

- **Amount basis.** Matching uses `amount_due`. Reports use `total_price`. They differ for orders with credit applied.
  This is the same difference as for "pay everything" today.
- **Not one transaction.** The orders are set one by one, each only while still `awaiting_payment`. A concurrent change
  can leave part of the set unpaid. The admin is told which orders were not paid and can run the flow again.
- **Rounding.** Amounts are rounded to cents per order. A total with more than two decimals can differ by one cent from
  the sum the customer sees. The proposal shows the rounded amounts.
- **Search limit.** More than 60 payable orders, or more than €100 000 open, cannot be searched. The admin must then pay
  those orders with the existing buttons or `/edit_order`.
- **Button width.** Two buttons in one row can shorten a long customer name on small screens. If this is a problem in
  the test environment, put the amount button in its own row. The callback data is the same.
- **Only approved customers** appear in the list, as today. An open order of a customer who is no longer approved can only
  be paid with `/edit_order`.

## 7. Test plan summary

| Area | Tests |
|---|---|
| Parsing and matching | PP-1 |
| Proposal, confirmation, concurrency | PP-2 |
| Customer message | PP-3 |
| Buttons, prompt, callbacks | PP-4 |
| Overview command and menu | PP-5 |
| Docs and changelog | PP-6 |

Before the final merge run `scripts/static-analysis.sh`, the full `pytest` suite, and the manual check in section 5.
