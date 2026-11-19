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
- [x] **H3. The admin is never told that a user could not be notified** (`user_commands.py`, approve and reject,
  three copies). The fallback is in an `except` around `_send_message`, which never raises: it returns
  `{"success": False}`. The fallback text itself is hard-coded English, holds the user's contact details and the raw
  exception text. **Done**: one helper checks the send result and tells the admin, translated, only the name.
- [x] **H4. Names show up as `&amp;` and `&lt;` in the admin's user lists** (`user_commands.py`: `/list_pending`,
  `/list_users`, `/user_status`, `/list_guests`). The names are HTML-escaped, but the messages are sent as plain text,
  so the escaping is visible. **Done**: plain text, not escaped.
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
- [x] **H8. Cancelling orders from the box audit always fails** (`boxes.py`, `_cancel_excess_orders`, found by the
  tests for H6). It built an `AdminOrderCommands` and called `_execute_cancel` on it, but that class is a facade
  without the method: the "cancel orders" button raised an `AttributeError`. **Done**: `_execute_cancel` lives in
  `BaseHandler` and tells the customer in their own language.
- [x] **H9. A pickup location with `&` or `<` breaks the payment message** (`delivery_overview_handler.py`,
  `_build_delivery_message`, found by the tests for H6). The message is sent as HTML, but the location was not
  escaped, so Telegram can refuse the whole message. **Done**: escaped.

## Medium priority

- [x] **M1. `_handle_edit_reply` is a 30-branch `if` chain** (`bot_service.py`, complexity 35). Each answer to a text
  prompt is routed by `edit_type`; some branches also parse and validate the input (a quantity, a box count). Make it
  a table of edit types, like `COMMAND_ROUTES`, and move the parsing to the handlers. `process_update` (11) loses the
  inline document and media-group handling along the way. **Done**: `ANSWER_ROUTES`
  (`services/routing/edit_reply_table.py`); the quantity, box count and description formatting are read by the
  handlers; `process_update` reads the edit context once (it was read twice) and hands documents and photos to small
  methods. A test fails for a stored prompt type that nothing answers, which found the dead `edit_supplier_input`.
- [x] **M2. `/list_boxes` reads per offer and per box** (`boxes.py`, `handle_list_boxes`, complexity 23): the boxes of
  every offer one by one, then the orders of every listed box. The status filter is a chain of `and`/`or`. **Done**:
  one scan of the boxes, one status-index query for the boxes ready for labeling, a filter table, and the audit's
  offer selection reads the suppliers once.
- [x] **M3. Processing a wholesale order is one 230-line function** (`management.py`, complexity 27): planning (which
  order fits), writing, box clean-up and the summary are mixed. The "more offers to process?" check and the offer
  selection read the orders of every offer one by one, and the offer selections (`management.py`, `boxes.py`) scan
  the suppliers once per offer. **Done** for `management.py`: the plan is a pure function
  (`services/wholesale_plan.py`), the handler applies it in small steps, and the pending orders of all offers are read
  once through the status index. The `boxes.py` selection follows with M2.
- [x] **M4. The delivery workflow searches every offer for one box** (`wholesale_delivery_handler.py`,
  `handle_partial_action`, `_continue_workflow_after_action`): it reads the boxes and orders of all offers to find a
  box whose id it already knows (or knows the start of). **Done**: one read of the box (`get_box`), or one scan of the
  boxes when only the start of the id is known.
- [x] **M5. Text that bypasses the translations**: "(Page x/y)", "◀️ Prev", "Next ▶️" (`management.py`);
  "⏳ Delayed", "⏳ Remaining Delayed" and the English words passed into `partial_delivery_processed`
  (`wholesale_delivery_handler.py`); "(no username)", "User", "matching '…'", "First name", "Last name", "Status:"
  (`user_commands.py`); "units" in the audit proposal (`boxes.py`); the raw order status in the duplicate-order warning
  (`customer/order_commands.py`). **Done**, per file, with the fixes above.
- [x] **M6. Handlers build other handlers to call their private methods**: the box audit builds `AdminOrderCommands`
  for `_execute_cancel` (`boxes.py`), `/payment_info` builds a `DeliveryOverviewHandler` (and with it a Lambda client)
  for `_build_delivery_message` (`customer/order_commands.py`), and the supplier prompt calls
  `supplier_commands._create_supplier` (`bot_service.py`). Done for `boxes.py` (`_execute_cancel` in `BaseHandler`)
  and `customer/order_commands.py` (`PaymentMessageMixin`); `bot_service.py` with M1 (`SupplierCommands.create_supplier`
  is public). **Done.**
- [x] **M7. Duplicated code**: rejecting a user (two copies) and showing a user's status (two copies, one with a
  hard-coded "Status:") in `user_commands.py`; choosing which orders to cancel (proposal and execution) in `boxes.py`;
  deleting cancelled and deleting completed orders in `customer/order_commands.py`; storing the delivery context next
  to `EditContextManager` and two identical branches in `wholesale_delivery_handler.py`. Status literals (`"pending"`,
  `"ordered"`) are used where `OrderStatus`/`BoxStatus` exist. **Done**: one copy each, and the last status literals
  in these files (`database.py`) use the enums. (The `"active"` left in `callback_handler.py` and `boxes.py` is the
  name of a list filter, not a status.)
- [ ] **M8. Left over from the first audit, in these files**:
  - [x] **a.** The admin offer views (overview, edit interface) live in the customer `InfoCommands`, and
    `view_offer_<id>_edit` is a customer route gated inside the handler. **Done**: the edit screen is
    `OfferCommands.handle_edit_offer_interface`, behind its own admin-only route; the customer route is
    `view_offer_<id>` only. The admin's `/list_offers` overview stays in `InfoCommands`: it is the same command and
    builds the same lines as the customer list, so splitting it would only move the `_is_admin` check.
  - **b.** Audit logging (purchase events) is triggered from the data layer (`database.py`), which therefore depends
    on a service that depends on it.
  - **c.** The inline re-edit of offer announcements (`sync_offer_messages` and helpers) is domain logic in
    `BaseHandler`.

## Order of work

Tests first for every file that changes (H6), then the fixes per file, bugs before structure: H7, H5, management
(H1, H2, M3, M5), user commands (H3, H4, M5, M7), boxes (M2, M5, M6, M7), wholesale delivery (M4, M5, M7), customer
orders (M5, M6, M7), the bot service (M1, M6) and last the leftovers (M8).
