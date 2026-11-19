# Code quality audit 3: what the bot sends

Status: **in progress** (2026-11-19). Follows two earlier audits (of the four, then the ten largest files; see the
git history of `docs/`), which are done. Most of what remains wrong shows up in the messages people get:
announcements, notifications from the Lambdas, the admin's order screens and the texts typed into the bot. This audit
follows those messages through the code that the first two left alone, and adds to-dos from the owner. Same
priorities as before:

- **High**: wrong behaviour, a security or privacy risk.
- **Medium**: a structural problem with a clear payoff (duplication, repeated reads, text that bypasses the
  translations).

## Scope

| Area                                  | Files                                                                                     |
|---------------------------------------|-------------------------------------------------------------------------------------------|
| Offer announcements to subscribers    | `src/notification_sender.py`, `src/services/offer_message_sync.py`                        |
| Messages sent by the Lambda           | `src/message_sender.py`                                                                   |
| Typed input that ends up in a message | `src/utils/telegram_entities.py`, `src/handlers/admin/offer/editing.py`                   |
| Guests (customers without Telegram)   | `src/handlers/base_handler.py`, `src/repositories/customer_repository.py`                 |
| The admin's order screens             | `src/handlers/admin/order/*.py`                                                           |
| Lists and reports                     | `src/handlers/customer/info_commands.py`, `src/services/reporting.py`                     |
| Workflow lookups                      | `src/services/database.py` (`get_boxes_by_offer_with_order_status`)                       |

## High priority

- [x] **A0. Placing an order for a customer always ends in an error** (`order/order_placement.py`, found while fixing
  A3). After the order is written and the customer is told, the handler calls
  `CustomerOrderCommands._notify_channel_order`, which no longer exists (since the revert of the milestone
  notifications, 2026-04-01). The `AttributeError` skips the group announcement and the admin's confirmation, and the
  admin sees the order fail, although it was placed. **Done**: `CustomerOrderCommands.announce_order_for` announces
  the order in the group (not for guests, as the comment of the group sender says); `tests/test_order_for_flow.py`
  runs the whole flow and fails on the old call.
- [x] **A1. The first subscriber DM of an offer is built by hand, without escaping the name**
  (`notification_sender.py`, `_send_notification_to_customer`). The group post and every later re-edit of the same DM
  come from `OfferMessageBuilder`, which escapes the name; the first DM builds its own HTML with `offer.name` as
  stored. A name with an HTML tag (the name check allows Telegram's tags) or `&` shows differently in the first DM
  than after any re-edit, or makes Telegram refuse the message for every subscriber. Fix: render the DM with
  `OfferAnnouncements.render`, so the first message and its re-edits are the same. **Done** with `OfferMessageBuilder`
  itself, translated for the subscriber, so the order buttons of the first DM stay in the subscriber's language (the
  re-edits use the group language, as before). An empty description no longer shows as "None".
- [x] **A2. The formatting of a typed description lands on the wrong characters** (`utils/telegram_entities.py`).
  Telegram counts entity offsets in UTF-16 code units; `entities_to_html` cuts the Python string by code points. Every
  emoji outside the basic plane (🍺, 🍻) before a bold or italic word shifts the tags one place, so they cut through a
  word. The text around the entities also goes into the HTML without being escaped. Fix: convert in UTF-16 units and
  escape the text between the tags. **Done**: the tags are placed in one pass over the UTF-16 text, so nested
  entities also stay nested (the old code dropped the outer tag's text). A description typed without formatting is
  kept as typed, so tags typed by hand still work (the HTML check of the description guards them).
- [x] **A3. Messages to guests are only skipped for the id -1, but guests get -2, -3, ...**
  (`base_handler.py` `_send_message`, `_send_photo`, `_send_media_group`; `message_sender.py` `send_from_admin`). The
  customer repository numbers guests with negative ids (`-next_id`). The guard is meant to keep guest messages away
  from Telegram; it now lets every guest but the first through, and the failures reach the admin as delivery errors.
  Fix: one check, "a guest or a negative id", where messages go out. **Done**, but not in `_send_message`: groups
  have negative ids too, so it cannot tell a guest from a group. The one sender that wrote to a customer's id without
  looking (the confirmation of "order for") uses `_notify_customer`, which skips guests; the message Lambda, which
  only writes to users, skips every id that is not positive.

## Medium priority

- [ ] **B1. The message Lambda sends every bot message at once** (`message_sender.py`, `send_messages`). Bot messages
  go out with one `asyncio.gather`, with no limit; a batch of 50 payment overviews runs into Telegram's rate limit
  (about 30 messages a second) and the 429s come back as failures. The admin messages are already sent in batches of
  five. Fix: the same batching for bot messages, and a retry after a 429 with its `retry_after`.
- [ ] **B2. The failure report of the message Lambda is hard-coded English** (`message_sender.py`,
  `notify_admin_of_failures`), and `notification_sender.py` hard-codes the admin's Telegram id (`15005473`) instead of
  `ADMIN_USER_ID`. Fix: translated texts; the id from `config.py`.
- [ ] **B3. The admin's order screens bypass the translations**: "❌ Cancel Order for …", "◀️ Previous", "Page x/y",
  "Next ▶️" (`order/order_cancellation.py`); " - Page x/y" (`order/base_order_handler.py`). Status literals
  (`"pending"`, `"ordered"`, `"cancelled"`, `"completed"`) are used throughout `order/*.py`, `import_handler.py` and
  `offer/notifications.py` where `OrderStatus` exists, and the `/list_user_orders` status filter is a chain of
  `and`/`or` (`order/order_viewing.py`).
- [ ] **B4. Five copies of "read the customer of a button, or say it is gone"** (`user_commands.py`:
  `handle_edit_user_select`, `handle_user_status_select`, `handle_approve_user_select`, `handle_approve_user_by_id`,
  `handle_reject_user_by_id`). Fix: one helper. `InfoCommands.handle_list_my_orders` builds a `BaseOrderHandler` to
  call one method (the pattern of M6 in the previous list).
- [ ] **B5. The workflow box lists read the orders of every box** (`database.py`,
  `get_boxes_by_offer_with_order_status`): one query per box, for each step of the wholesale delivery and labeling
  workflows. Fix: one query of the offer's orders, grouped by box.

- [ ] **B6. mypy does not look inside untyped functions** (`check_untyped_defs` is off), which is how A0 survived
  seven months: the call to a method that did not exist was in a function without annotations. Fix: turn it on and
  fix what it finds, or annotate the handler methods that call other handlers.

## To-do (owner)

- [x] **T1. `/list_offers` with an unknown filter says nothing about it.** `/list_offers cancelled` shows the default
  list as if no filter was given. Acknowledge the unknown word (and name the filters that exist) above the list.
  **Done**: a note names the word and points to `/list_offers help`, before the first page of the default list. The
  known words are per audience (`offer_listing.is_known_filter`): an admin filter typed by a customer is unknown.
- [x] **T2. Leave two more customers out of the reports**: `8a1bdd6b-c3c0-403d-9f49-b2f9acb738d4` and
  `bc63908b-8f10-45a8-bb3e-cb89e5ea7e94` join `EXCLUDED_CUSTOMER_IDS` (`services/reporting.py`). **Done.**
- [ ] **T3. Refill boxes after cancellations without editing the database by hand.** After orders are cancelled, an
  offer (not completed, not inactive) can have gaps in its earlier boxes while later boxes hold orders that would fit
  there. An admin-only tool moves orders from later boxes into the empty places of earlier ones, so fewer boxes are
  needed. A bot command if that is as simple as a script in `scripts/`; otherwise the script.

## Order of work

The to-dos first (small and asked for), then the bugs per file with a test that fails before the fix: A3, A1, A2,
then B1, B2 (the Lambdas), B3, B4 and last B5.
