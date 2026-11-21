# Instant Orders: Technical Design

Status: implemented (2026-11-21). The use cases are in
[instant-orders-and-partial-payments.md](instant-orders-and-partial-payments.md). This document says how to build
them, in small steps that each leave the bot working and the tests green.

## 1. What the current system already does

An instant offer needs one thing that the bot cannot do today: create an offer, a delivered box and a delivered order
in one step. Everything after that already exists, because the same state occurs after a partial wholesale delivery:
an `active` offer with a `delivered` box that has free units.

| Need (use case) | What the code does today | Change |
|---|---|---|
| Later orders go straight to `ready_for_labeling` (UC1.4) | `CustomerOrderCommands._find_or_create_box` prefers delivered boxes with room. `_create_and_assign_order` gives an order on a delivered box status `ready_for_labeling` and `received_quantity = quantity`. | None |
| No second box is created (UC1.4) | `_find_or_create_box` creates no box while a delivered box exists. | None |
| Offer is `active` with room, `sold_out` without (UC1.5) | `BoxStatusManager.update_offer_status_after_change` counts only the free room in delivered boxes when one exists. | None |
| Announcement loses and regains its order button (UC1.3, UC1.7) | `BaseHandler._check_offer_status_after_change` calls `sync_offer_messages` when the status changes. | None |
| Editing name, price, description (UC1.6) | `/update_offer_*` re-render the tracked announcements. | None |
| `/instant_order` box size 1 to 6 | `OfferBaseHandler.VALID_BOX_SIZES` already contains 1 to 6. | None (the README sentence about wholesale sizes is out of date) |
| Offer completes after labeling | `LabelingCompletionHandler._check_and_update_offer_status` completes a `sold_out` offer when all boxes are delivered and labeled. | None |

Conclusions:

- **No flag on the offer.** After creation, an instant offer is an ordinary offer. No later behavior depends on how it
  was created, so there is no `is_instant` field and no change to `Offer`, `OfferRepository` reads, the cache or the
  API. Only the creation step is new.
- **No new table, index, Lambda, environment variable or IAM change.** `template.yaml` stays as it is.
- `/publish_offer` auto-orders one unit for the admin. `/instant_order` does not, because the first order is the
  customer's.

## 2. Decisions

### D1. Cancelling an order that is `ready_for_labeling` (decided: B)

UC1.7 says the admin can cancel an instant order and the unit becomes free again. The bot refuses this today.
`BaseHandler._refuse_cancel` only allows `pending` and `ordered` orders (`ACTIVE_ORDER_STATUSES`, audit 6 A2). A first
instant order is already `ready_for_labeling`, so it can never be cancelled. A wrong customer cannot be undone. A wrong
price can be corrected with `/edit_order`.

| Option | Effect |
|---|---|
| A. Keep the rule | UC1.7 does not hold. A mistaken instant order stays. Remove UC1.7 from the use cases. |
| B. Also allow cancel at `ready_for_labeling` (recommended) | UC1.7 holds. It applies to every order in that status, regular offers too. No money is involved yet: credit is applied at the delivery overview, after `labeling_completed`. Orders from `labeling_completed` onward stay refused. |

Option B is the decision. IO-10 implements it.

### D2. An instant offer that never fills (decided: no command)

A box of 4 with one order stays `active` and keeps its group announcement until all units are ordered. The bot has no
command to close it: `/offer_status` only sets `import`, and `/cancel_offer` is guarded by IO-9. This is the intended
behavior of "customers can order while there is room". The admin sells the offer out by placing an order for the last
free units (`/order_for`). No `/close_offer` command is added.

## 3. Behavior details

**Command.** `/instant_order <supplier> <offer name> <price> <customer> [box_size]`.

- Supplier: the first word, as in `/create_offer`. It must exist and be `active`.
- Name, supplier and customer can be quoted. Straight quotes and the curly quotes that Telegram clients insert
  (`“ ”`) both work. The router already splits on spaces, so the handler joins the words and tokenizes again.
- Without quotes, the grammar is read from the end: a bare whole number from 1 to 6 after the customer is the box size
  when the word three places from the end is a price. Otherwise the last word is the customer and the box size is 1.
  Everything between the supplier and the price is the name.
- Price: a positive number with at most two decimals. A comma is accepted as the decimal sign.
- Box size: a whole number from 1 to 6. Default 1.
- Customer: fuzzy match, `approved` customers only (guests are `approved`). No match gives an error. More than one match
  gives a list. The admin picks one, and the other input is kept in an edit context (same pattern as `/credit`).

**Created in one write:** the offer, one box and the first order.

| Entity | Values |
|---|---|
| Offer | `supplier_name`, `name`, `price_per_unit`, `wholesale_box_size = box_size`, status `sold_out` when `box_size == 1`, else `active` |
| Box | `max_capacity = box_size`, `current_quantity = 1`, status `delivered` |
| Order | `quantity = 1`, `received_quantity = 1`, status `ready_for_labeling`, `placed_by_admin = True`, prices from the offer |

After the write, the bot records the `ORDER_CREATED` purchase event, as every other order creation does.

**Messages.**

- Admin: a confirmation with the offer ID, name, price, box size, customer and order status. When there is room, it
  also shows the line to use for more orders (`/order_for <customer> <offer_id>`).
- Customer: the existing `admin_order_placed` message (a guest gets none, as today). The status text is the translated
  `ready_for_labeling`.
- Group: only when `box_size > 1`. One rich offer announcement with the order buttons, through
  `_send_rich_offer_message(..., force_group=True)`, which also tracks the message for later edits. No message that names
  the customer. No subscriber message. For `box_size == 1` nothing goes to the group.

## 4. Atomic changes

Each change is one commit. Run `scripts/static-analysis.sh` and the full test suite after each. Order matters only where
`Depends on` says so.

### IO-1. `/order_for` matches approved customers only

- **Why:** use case rule. Today `/order_for` also matches pending and rejected customers (bug).
- **Files:** `src/handlers/admin/order/order_placement.py`.
- **Change:** pass `status_filter="approved"` to every `_find_customer_with_disambiguation` call in the file.
- **Tests:** `tests/test_order_for_flow.py`. A pending and a rejected customer named like the search word are not
  matched and not listed. An approved customer is matched. A guest is matched.
- **Commit:** `fix: match only approved customers in /order_for`

### IO-2. Cover orders on a delivered box with free units

- **Why:** the design relies on existing behavior (section 1). Tests prove it and protect it.
- **Files:** `tests/test_instant_offer_state.py` (new). First check `tests/test_delivered_box_availability.py` and
  `tests/test_wholesale_partial_delivery.py`, and add only what they do not cover.
- **Change:** none in `src/`. A fixture creates the state: offer `active` with `wholesale_box_size = 4`, a `delivered`
  box with `current_quantity = 1`, and one `ready_for_labeling` order.
- **Tests:**
  1. A customer order goes into that box with status `ready_for_labeling` and `received_quantity == quantity`. No box
     is created. The offer stays `active`.
  2. The order that fills the box makes the offer `sold_out`, and the tracked group message is edited (marker, no buttons).
  3. The admin path (`/order_for`) gives the same result.
  4. Labeling completes the offer only when it is `sold_out`.
  5. A customer cannot order more than the free units.
- **Commit:** `test: cover orders on a delivered box with free units`

### IO-3. Parser for the `/instant_order` arguments

- **Files:** `src/services/instant_order_input.py` (new), `tests/test_instant_order_input.py` (new).
- **Change:** a pure function, no database and no Telegram.

```python
@dataclass(frozen=True)
class InstantOrderInput:
    supplier: str
    offer_name: str
    price: Decimal
    customer: str
    box_size: int


class InstantOrderInputError(ValueError):
    key: str  # a translation key, for example "instant_order_price_invalid"


def parse_instant_order(words: list[str]) -> InstantOrderInput: ...
```

- **Rules:** tokenizer `"([^"]*)"|“([^”]*)”|(\S+)`. A quoted token is never read as a price or box size. Errors:
  `usage_instant_order` (fewer than four tokens), `instant_order_price_invalid`, `instant_order_box_size_invalid`.
- **Tests (table driven):** quoted and unquoted forms; curly quotes; a name with a number (`Tripel 8`); box size present
  and absent; comma price; price with three decimals; zero and negative price; box size 0, 7, `x`; a numeric customer
  ID of 8 digits; a customer with spaces in quotes; too few words.
- **Commit:** `feat: parse the instant order arguments`

### IO-4. Create offer, box and order in one write

- **Depends on:** none.
- **Files:** `src/repositories/offer_repository.py`, `src/services/database.py`,
  `tests/test_repositories/test_offer_repository.py`, `tests/test_instant_offer_creation.py` (new).
- **Change:**
  - `OfferRepository.create_with_box_and_order(offer, box, order) -> bool`: allocate the offer ID with
    `system_repo.get_next_id("offer_id")`, set `offer.offer_id`, `box.offer_id`, `order.offer_id` and `order.box_id`, then
    one `transact_write_items` with three `Put` items (offers, boxes, orders), each with `attribute_not_exists` on its key.
    Same low-level client and `TypeSerializer` pattern as `OrderRepository.create_with_box_increment`. The box item is
    written with `current_quantity` already set, so no increment is needed. Invalidate `OfferCache` after a commit.
  - `DynamoDBService.create_instant_offer(offer, box, order) -> bool`: call the repository, then record `ORDER_CREATED`
    (as `create_order_with_box_increment` does, and logged, not raised, when the event fails).
- **Why one write:** a failure between three separate writes would leave an offer without an order or a delivered box
  without its units. A gap in the offer ID counter after a failed write is harmless.
- **Tests (moto):** all three items exist after success. A rejected transaction (an existing key) writes none and returns
  `False`. A `ClientError` returns `False` and writes none. The offer is visible to `get_offer` straight away (cache).
- **Commit:** `feat: create an offer, box and order in one transaction`

### IO-5. The `/instant_order` handler (without announcement)

- **Depends on:** IO-1, IO-3, IO-4.
- **Files:** `src/handlers/admin/offer/instant.py` (new, `InstantOrderHandler(OfferBaseHandler)`),
  `src/handlers/admin/offer/__init__.py` (add it to `OfferCommands`), `src/translations/en.json`, `nl.json`,
  `tests/test_instant_order_command.py` (new).
- **Change:**
  - `handle_instant_order(chat_id, args)`: parse (IO-3), validate the name with `_validate_offer_name` and the supplier
    with `_validate_supplier`, find the customer with `status_filter="approved"` and the callback prefix
    `instant_order_customer`, create the entities (section 3), call `db.create_instant_offer`, send the admin
    confirmation and the customer message (`_notify_customer(customer, "admin_order_placed", ...)`, with the
    `pm_notification_failed` line as `/order_for` does).
  - More than one match: store an `EditContext` of type `instant_order_customer_select` whose `entity_id` is the JSON of
    the parsed input, and show the list. `handle_instant_order_customer_select(chat_id, customer_id)` reads the context,
    deletes it, and creates the order. Same pattern as `CreditCommands.handle_credit_customer_select`. An expired context
    gives `instant_order_context_expired`.
  - Without arguments: send `usage_instant_order` (IO-8 replaces this with the guided flow).
  - Not wired to a command yet, so no user can reach it. Tests call the handler directly.
- **New translation keys (en and nl, flat style as the existing keys):** `usage_instant_order`,
  `instant_order_created`, `instant_order_created_with_room`, `instant_order_price_invalid`,
  `instant_order_box_size_invalid`, `instant_order_context_expired`, `failed_instant_order`.
- **Tests:** box size 1 gives a `sold_out` offer, a `delivered` box with quantity 1 and a `ready_for_labeling` order for
  the matched customer. Box size 4 gives an `active` offer. No match: error and nothing created. Two matches: list shown,
  nothing created until a pick. Pending or rejected customers are not matched. A guest is matched and not messaged.
  Retired or unknown supplier, bad price, bad box size, bad name: error and nothing created. The customer message is in
  the customer's language. The `ORDER_CREATED` event exists. No admin auto-order is created.
- **Commit:** `feat: add the instant order handler`

### IO-6. Group announcement for an instant offer with free units

- **Depends on:** IO-5.
- **Files:** `src/handlers/admin/offer/instant.py`, `tests/test_instant_order_command.py`.
- **Change:** after a successful creation with `box_size > 1`, call `expire_exports()` and
  `_send_rich_offer_message(int(DEFAULT_GROUP_ID), offer, force_group=True, include_buttons=True)`. Do not call
  `_notify_subscribers_rich`. When `DEFAULT_GROUP_ID` is not set, skip silently, as `_announce_offer` does.
- **Tests:** box size 4: exactly one group message with the order buttons, and a `group` notification row for the offer.
  A subscriber receives nothing. Box size 1: no group message. In no case does a group message name the customer. A
  later order that fills the box edits the announcement (covered by IO-2, add one end-to-end check here).
- **Commit:** `feat: announce an instant offer with free units in the group`

### IO-7. Make `/instant_order` available

- **Depends on:** IO-5, IO-6.
- **Files:** `src/services/routing/command_table.py`, `src/services/callback_handler.py`, `telegram-commands.json`,
  `src/translations/en.json`, `nl.json` (`help_offers`), `README.md`, `tests/test_command_routing.py`.
- **Change:**
  - `"/instant_order": admin_command("offer", "handle_instant_order", private_rest)`.
  - Callback `^instant_order_customer_(.+)$` calls `handle_instant_order_customer_select` (admin only, keyboard removed).
  - `telegram-commands.json`, admin menu, alphabetical (after `import_orders`): `instant_order`, "Create an offer and an
    order at once: <supplier> <name> <price> <customer> [box_size]".
  - `help_offers`: one line for `/instant_order`.
  - README: the command in the admin list, a short "Instant orders" section under Features, and a corrected box size
    statement (the code accepts 1 to 6, 8, 9, 10, 12, 15, 16, 18, 20, 24).
- **Tests:** `test_command_menu.py` and `test_command_routing.py` already check that the menu matches the table and that a
  customer gets no answer for an admin command. Add an explicit case for `/instant_order`.
- **Commit:** `feat: add the /instant_order command`

### IO-8. Guided input when no arguments are given

- **Depends on:** IO-7.
- **Files:** `src/handlers/admin/offer/instant.py`, `src/services/routing/edit_reply_table.py`,
  `src/services/callback_handler.py`, `src/translations/en.json`, `nl.json`, `tests/test_instant_order_guided.py` (new).
- **Change:** `/instant_order` without arguments starts these steps. Each step keeps what was entered in the edit
  context (`entity_id` is JSON), so there is no other state.
  1. Supplier: buttons for the active suppliers (`instant_order_supplier_<supplier_id>`).
  2. Name: text prompt (edit type `instant_order_name`).
  3. Price: text prompt (`instant_order_price`). An invalid price asks again.
  4. Customer: text prompt (`instant_order_customer`). Then the same match rules as IO-5, with the same list.
  5. Box size: buttons 1 to 6 (`instant_order_box_<n>`). Then the order is created.
  `/cancel` clears the context (existing behavior of `_handle_cancel_command`).
- **New `ANSWER_ROUTES`:** `instant_order_name`, `instant_order_price`, `instant_order_customer`, all to the `offer`
  handler.
- **Keys:** `choose_instant_order_supplier`, `enter_instant_order_name`, `enter_instant_order_price`,
  `enter_instant_order_customer`, `choose_instant_order_box_size`, and the matching `placeholder_*` keys.
- **Tests:** the full path ends with the same entities as IO-5. A lost context gives `instant_order_context_expired`.
  Invalid price asks again. `/cancel` ends the flow. A non-admin tap on a button does nothing.
- **Commit:** `feat: guide the admin through /instant_order step by step`

### IO-9. Do not cancel an offer that has delivered orders

Ship this before IO-7. It removes the main way to damage an instant offer.

- **Why:** `handle_cancel_offer` sets the offer `inactive` and deletes all its boxes when no order is `pending` or
  `ordered` (`BoxDeletionService.delete_offer_boxes`). For an offer with a delivered box, that deletes the box that holds
  delivered orders and leaves them without a box. This exists today for offers after a partial delivery, but every
  instant offer with free units is in this state, so it becomes common.
- **Files:** `src/handlers/admin/offer/management.py`, `src/translations/en.json`, `nl.json`,
  `tests/test_offer_management.py`.
- **Change:** in `handle_cancel_offer` and `handle_confirm_cancel_offer`, refuse when any box of the offer has status
  `delivered` and holds units. Send `offer_cannot_cancel_delivered` (offer ID and the reason). It applies to every offer, not
  only instant offers.
- **Tests:** an offer with a delivered box that holds an order is refused and keeps its boxes and orders. An offer with
  only `open`, `full` or `ordered` boxes is cancelled as before. The confirm callback is refused too.
- **Commit:** `fix: refuse to cancel an offer that has delivered boxes with orders`

### IO-10. Cancel an order that is `ready_for_labeling`

- **Files:** `src/models/entities.py`, `src/handlers/base_handler.py`,
  `src/handlers/admin/order/order_cancellation.py`, `src/handlers/admin/order/order_editing.py`,
  `tests/test_cancel_order_flow.py`, `tests/test_edit_order_callback_dispatch.py`.
- **Change:**
  - `models/entities.py`: add `CANCELLABLE_ORDER_STATUSES = (*ACTIVE_ORDER_STATUSES, READY_FOR_LABELING)`. Do not change
    `ACTIVE_ORDER_STATUSES`: it also drives the order limits, the `active` export and `/cancel_offer`.
  - `BaseHandler._refuse_cancel`, the order list of `_show_user_orders_for_cancel` and `OrderEditing._status_options`
    use the new constant.
  - `cancel_order_with_box` stays as it is. It already decrements the box by the order's quantity and checks the order
    status it read. The box keeps status `delivered`. `_check_offer_status_after_change` reopens a `sold_out` offer and
    edits the announcement.
- **Tests:** cancelling a `ready_for_labeling` order frees the unit, keeps the box `delivered`, reopens a `sold_out` offer
  (announcement gets its buttons back) and notifies the customer. Orders in `labeling_completed`, `awaiting_payment`,
  `completed` are still refused. A second tap on the same confirmation changes nothing. The `active` export filter and the
  5-unit limit do not count the cancelled order as active (unchanged).
- **Commit:** `feat: allow cancelling an order that is ready for labeling`

### IO-11. Admin panel button

- **Depends on:** IO-8.
- **Files:** `src/handlers/admin/admin_commands.py`, `src/services/callback_handler.py`, `src/translations/en.json`,
  `nl.json`, `tests/test_admin_screens_language.py`.
- **Change:** a button `instant_order_btn` in the Offers menu (`handle_admin_offers`) with callback
  `cmd:instant_order`, registered in `_register_panel_command_routes` as `handlers["offer"].handle_instant_order(chat, [])`.
- **Tests:** the Offers menu has the button in both languages. Tapping it starts the guided flow.
- **Commit:** `feat: add instant order to the admin panel`

### IO-12. Changelog and use case status

- **Files:** `src/handlers/customer/changelog_commands.py`, `docs/instant-orders-and-partial-payments.md`.
- **Change:** an admin-facing changelog bullet for `/instant_order`, in a new entry titled with the release date.
  `tests/test_changelog.py` checks the page length and the HTML balance. Set the status line of the use case document to
  "implemented".
- **Commit:** `docs: add instant orders to the changelog`

## 5. Deployment

- No data migration, no new table, no new environment variable.
- Deploy with `./deploy.sh test`, check, then `./deploy.sh prod`. The script runs `setup-commands.sh`, which adds
  `/instant_order` to the admin menu.
- Check in the test environment: `/instant_order` with box size 1 and with box size 4, an order from a second customer
  through the group button, `/process_labeling`, then the delivery overview.

## 6. Risks and limits

- **Quotes.** Telegram clients can replace `"` with curly quotes. The parser accepts both. A name that contains a quote
  character cannot be entered in the one-line form. Use the guided flow.
- **Unquoted customer with spaces** is read as part of the name or as an invalid price. The error text tells the admin to
  quote the customer.
- **`/create_box` on an offer with a delivered box** adds an `open` box next to it (existing behavior, not changed).
  Once the delivered box is full, new orders go to the open box as `pending` orders. This is not specific to instant
  offers.
- **Price precision.** The price is stored as `Decimal` with two decimals. The order total is the price times 1.

## 7. Test plan summary

| Area | Tests |
|---|---|
| Matching | IO-1 |
| Existing behavior that is relied on | IO-2 |
| Parsing | IO-3 |
| Atomic write | IO-4 |
| Command, messages, announcement | IO-5, IO-6 |
| Routing and menu | IO-7 |
| Guided flow | IO-8 |
| Safety | IO-9, IO-10 |
| Panel and docs | IO-11, IO-12 |

Before the final merge run `scripts/static-analysis.sh`, the full `pytest` suite, and the manual check in section 5.
