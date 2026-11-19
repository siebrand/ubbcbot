# Code quality list: the ten largest files in `src/`

Status: **in progress** (2026-11-19). Follows [code-quality-audit.md](code-quality-audit.md), which covered the four
largest files. This list takes the ten largest files and keeps only the high and medium priority items:

- **High**: wrong behaviour, a security or privacy risk, or a core money path without tests.
- **Medium**: a structural problem with a clear payoff (complexity, repeated reads, duplication, text that bypasses
  the translations).

Low priority items (naming, comments, small style issues) are left out on purpose.

## Scope

| File                                               | Lines | Coverage | Functions over complexity 10                         |
|----------------------------------------------------|------:|---------:|------------------------------------------------------|
| `src/services/callback_handler.py`                 |   887 |    98.1% | —                                                    |
| `src/handlers/admin/offer/boxes.py`                |   620 |    21.2% | `handle_list_boxes` (23)                             |
| `src/handlers/admin/user_commands.py`              |   610 |    37.6% | —                                                    |
| `src/handlers/admin/offer/management.py`           |   554 |    32.8% | `handle_confirm_process_wholesale` (27)              |
| `src/handlers/base_handler.py`                     |   480 |    91.4% | —                                                    |
| `src/services/bot_service.py`                      |   476 |    63.9% | `_handle_edit_reply` (35), `process_update` (11)     |
| `src/handlers/customer/info_commands.py`           |   467 |    91.6% | —                                                    |
| `src/services/database.py`                         |   462 |    73.4% | —                                                    |
| `src/handlers/admin/wholesale_delivery_handler.py` |   446 |    41.3% | —                                                    |
| `src/handlers/customer/order_commands.py`          |   433 |    26.4% | —                                                    |

## High priority

- [x] **H1. Processing a wholesale order leaves cancelled units in their box** (**done**) (`management.py`,
  `handle_confirm_process_wholesale`). Pending orders that do not fit are cancelled with `db.cancel_order`, and the
  order that only partly fits is reduced, but neither gives its units back to the box (a normal cancellation calls
  `update_box_after_order_cancellation`). A box that held a cancelled order keeps counting its units: it is never
  "empty", so it is not cleaned up, and the offer shows less room than it has.
- [x] **H2. Customers are told about a cut or cancelled order in Dutch, whatever their language** (**done**:
  `BaseHandler._notify_customer` translates for the customer and skips guests)
  (`management.py`). `order_updated_limited`, `order_cancelled_insufficient` and `order_cancelled_offer_cancelled`
  are translated without the customer. Guests (no Telegram) are sent the message too.
- [ ] **H3. The admin is never told that a user could not be notified** (`user_commands.py`, approve and reject,
  three copies). The fallback is in an `except` around `_send_message`, which never raises: it returns
  `{"success": False}`. The fallback text itself is hard-coded English, holds the user's contact details and the raw
  exception text.
- [ ] **H4. Names show up as `&amp;` and `&lt;` in the admin's user lists** (`user_commands.py`: `/list_pending`,
  `/list_users`, `/user_status`, `/list_guests`). The names are HTML-escaped, but the messages are sent as plain text,
  so the escaping is visible.
- [x] **H5. A failed update returns the exception text** (`bot_service.py`, `process_update`): `str(e)` can hold
  customer data. Same fix as for callbacks. **Done.**
- [ ] **H6. The core money paths are barely tested**: placing an order (`customer/order_commands.py`, 26%), processing a
  wholesale order and cancelling an offer (`management.py`, 33%), the box audit (`boxes.py`, 21%), approving users
  (`user_commands.py`, 38%) and processing deliveries (`wholesale_delivery_handler.py`, 41%). Characterization tests
  come first, before any change to these files.
- [x] **H7. The sold-out list says "last 7 days" but shows every sold-out offer** (`sold_out_offers_title`). Decision
  (owner): the list shows everything. Task: update the messaging (title in `nl.json` and `en.json`, and any help text
  or README line that says otherwise), and remove `list_sold_out_offers_recent` if nothing uses it. **Done**: the title
  is "🚫 UITVERKOCHT:" / "🚫 SOLD OUT:", the customer help mentions `/list_offers sold_out` ("Alle uitverkochte
  aanbiedingen"), and the unused `list_sold_out_offers_recent` is gone.

## Medium priority

- [ ] **M1. `_handle_edit_reply` is a 30-branch `if` chain** (`bot_service.py`, complexity 35). Each answer to a text
  prompt is routed by `edit_type`; some branches also parse and validate the input (a quantity, a box count). Make it
  a table of edit types, like `COMMAND_ROUTES`, and move the parsing to the handlers. `process_update` (11) loses the
  inline document and media-group handling along the way.
- [ ] **M2. `/list_boxes` reads per offer and per box** (`boxes.py`, `handle_list_boxes`, complexity 23): the boxes of
  every offer one by one, then the orders of every listed box. The status filter is a chain of `and`/`or`.
- [x] **M3. Processing a wholesale order is one 230-line function** (`management.py`, complexity 27): planning (which
  order fits), writing, box clean-up and the summary are mixed. The "more offers to process?" check and the offer
  selection read the orders of every offer one by one, and the offer selections (`management.py`, `boxes.py`) scan
  the suppliers once per offer. **Done** for `management.py`: the plan is a pure function
  (`services/wholesale_plan.py`), the handler applies it in small steps, and the pending orders of all offers are read
  once through the status index. The `boxes.py` selection follows with M2.
- [ ] **M4. The delivery workflow searches every offer for one box** (`wholesale_delivery_handler.py`,
  `handle_partial_action`, `_continue_workflow_after_action`): it reads the boxes and orders of all offers to find a
  box whose id it already knows (or knows the start of).
- [ ] **M5. Text that bypasses the translations**: "(Page x/y)", "◀️ Prev", "Next ▶️" (`management.py`);
  "⏳ Delayed", "⏳ Remaining Delayed" and the English words passed into `partial_delivery_processed`
  (`wholesale_delivery_handler.py`); "(no username)", "User", "matching '…'", "First name", "Last name", "Status:"
  (`user_commands.py`); "units" in the audit proposal (`boxes.py`); the raw order status in the duplicate-order warning
  (`customer/order_commands.py`).
- [ ] **M6. Handlers build other handlers to call their private methods**: the box audit builds `AdminOrderCommands`
  for `_execute_cancel` (`boxes.py`), `/payment_info` builds a `DeliveryOverviewHandler` (and with it a Lambda client)
  for `_build_delivery_message` (`customer/order_commands.py`), and the supplier prompt calls
  `supplier_commands._create_supplier` (`bot_service.py`).
- [ ] **M7. Duplicated code**: rejecting a user (two copies) and showing a user's status (two copies, one with a
  hard-coded "Status:") in `user_commands.py`; choosing which orders to cancel (proposal and execution) in `boxes.py`;
  deleting cancelled and deleting completed orders in `customer/order_commands.py`; storing the delivery context next
  to `EditContextManager` and two identical branches in `wholesale_delivery_handler.py`. Status literals (`"pending"`,
  `"ordered"`) are used where `OrderStatus`/`BoxStatus` exist.
- [ ] **M8. Left over from the first audit, in these files**:
  - **a.** The admin offer views (overview, edit interface) live in the customer `InfoCommands`, and
    `view_offer_<id>_edit` is a customer route gated inside the handler.
  - **b.** Audit logging (purchase events) is triggered from the data layer (`database.py`), which therefore depends
    on a service that depends on it.
  - **c.** The inline re-edit of offer announcements (`sync_offer_messages` and helpers) is domain logic in
    `BaseHandler`.

## Order of work

Tests first for every file that changes (H6), then the fixes per file, bugs before structure: H7, H5, management
(H1, H2, M3, M5), user commands (H3, H4, M5, M7), boxes (M2, M5, M6, M7), wholesale delivery (M4, M5, M7), customer
orders (M5, M6, M7), the bot service (M1, M6) and last the leftovers (M8).
