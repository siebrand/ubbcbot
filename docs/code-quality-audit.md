# Code quality audit: the four largest files in `src/`

Status: **proposal** (2026-11-18). Nothing below has been implemented yet.

The four largest Python files in `src/` hold almost a sixth of the code (3,010 of 17,384 lines). They are also the
files almost every change touches: every button goes through the callback handler, every message through the base
handler, every read and write through the database facade.

| File                                     | Lines | Coverage | Most complex function                       |
|------------------------------------------|------:|---------:|---------------------------------------------|
| `src/services/callback_handler.py`       |   903 |    93.2% | (none above 10)                             |
| `src/handlers/customer/info_commands.py` |   775 |    18.8% | `handle_list_offers` 51, `_send_offer_view` 19 |
| `src/services/database.py`               |   690 |    53.7% | (none above 10)                             |
| `src/handlers/base_handler.py`           |   642 |    60.8% | (none above 10)                             |

Coverage is from `pytest --cov`. Complexity is the McCabe score (`ruff check --select C901`, threshold 10).

The findings come first, per file and ranked by impact. The refactoring plan follows, as steps that can each ship on
their own with green tests.

## Findings

Labels: **bug** = wrong behaviour now; **risk** = works now, but breaks easily or under load; **maintainability** =
makes changes slower or riskier.

### `src/handlers/base_handler.py`: a base class that does everything

`BaseHandler` has 21 subclasses, and `BotService` builds about 20 of them for every request. Besides being a base
class, it is the Telegram client, the translation service, a set of validation wrappers and the offer-announcement
sync service.

1. **Maintainability: nine copies of the Telegram HTTP call.** `_send_message`, `_delete_message`,
   `_delete_message_result`, `_set_message_reaction`, `_edit_message_text`, `_send_document_message`, `_send_photo`,
   `_send_media_group` and `_get_bot_username` each build the URL, check the token, call `requests.post` with
   `timeout=20`, and parse and log the response themselves. Three more copies live in `callback_handler.py`, and more
   in `import_handler.py`, `media_handler.py` and `message_sender.py` (16 places build `api.telegram.org/bot` URLs).
   The rules that matter are copied with them, and not consistently:
   - The guest skip (`chat_id == -1`) is in `_send_message`, `_send_photo` and `_send_media_group`, but not in
     `_send_document_message` or `_edit_message_text`.
   - The production group block ("prod blocks non-forced group messages", see CLAUDE.md) is in the same three, but not
     in `_send_document_message`.
   - The `TEST - ` prefix is added to message text and to photo and document captions, but not to edited messages.
2. **Bug (latent): `_t` raises on a missing placeholder.** `message.format(**params)` (`base_handler.py:64`) raises
   `KeyError` when a translation uses a placeholder the caller didn't pass, and `IndexError`/`ValueError` on a stray
   `{` in a translation. One wrong translation edit then breaks a whole command. A missing key silently returns the
   key itself, which is fine.
3. **Risk: translations are loaded once per handler instance, not once per container.** `_translations` is an
   instance attribute (`base_handler.py:24`) and handlers are rebuilt on every request. So each request that
   translates in several handlers parses `nl.json`/`en.json` several times. A module-level cache, loaded once per
   container, is enough.
4. **Maintainability: offer-message sync is domain logic in the base class.** `sync_offer_messages`,
   `_build_offer_message`, `_edit_tracked_message`, `_sync_subscriber_messages_async` and
   `_check_offer_status_after_change` (`base_handler.py:528-642`) are about offers and notifications, not about
   handling commands. They are in the base class only because several handlers need them.
5. **Maintainability: dead and duplicated code.**
   - `DecimalEncoder` (`base_handler.py:623`) is defined, but the payload holds no `Decimal`.
   - `json`, `os` and `boto3` are imported again inside `_sync_subscriber_messages_async`.
   - `_escape_html` reimplements `html.escape`.
   - `_send_message_simple`, `_send_document`, `_build_pagination_keyboard` and `_paginate_list` are one-line wrappers
     kept "for backward compatibility".
6. **Risk: the Lambda name comes from the environment, not from the handler.**
   `_sync_subscriber_messages_async` reads `ENVIRONMENT` from `os.environ` (`base_handler.py:619-633`), while the
   handler has `self.environment`. That's fine in Lambda, but it is a second source of truth, and in tests it
   silently points at `test`.
7. **Risk: a presigned URL is logged in the test environment.** `_send_photo` logs the first 150 characters of the
   photo URL (`base_handler.py:453`), which for S3 images includes the signature.

### `src/services/callback_handler.py`: 60 lambdas and a second allowlist

The router itself is sound and well tested (93% coverage, and `tests/test_callback_dispatch.py` taps every button).
The problems are in how routes are declared.

1. **Risk: the authorization allowlist is separate from the routes.** `CUSTOMER_CALLBACK_PATTERN`
   (`callback_handler.py:15-25`) has to be kept in step with the routes registered further down by hand. A customer
   button added to the router but not to the pattern is refused, which is the safe direction. But nothing ties the
   two together, and the edit mode of `view_offer_*_edit` relies on a check in another file
   (`handle_view_offer` in `info_commands.py`).
2. **Maintainability: the routes call private methods of other classes.** `_execute_fill_boxes`,
   `_execute_fill_and_create`, `_execute_create_boxes`, `_execute_cancel_orders`, `_show_audit_offer_selection`,
   `_execute_audit_offer` (`callback_handler.py:250-281`), `info._show_fomo` (`:324`),
   `admin_order.viewing._show_user_orders` (`:430`) and `editing()._show_aspect_menu` (`:548`) are all private. So a
   rename in a handler breaks the callback handler without any warning from the IDE or ruff.
3. **Maintainability: whether to remove the keyboard after a tap is decided apart from the route.**
   `_should_remove_keyboard` (`callback_handler.py:771-781`) and the `process_payment_` special case (`:734-739`)
   decide by prefix, so a new route gets the default behaviour unless someone remembers this list. The function also
   has a redundant branch: `page_info` is tested twice.
4. **Bug: a hard-coded English placeholder, and a context created behind the manager's back.**
   `_request_cancellation_reason` (`callback_handler.py:886-899`) creates an `EditContext` directly instead of through
   `EditContextManager`, and sets `input_field_placeholder` to `"Enter reason"`, which doesn't follow the translation
   convention.
5. **Maintainability: a second `BaseHandler` just to translate and send.** `CallbackHandler` lazily builds its own
   `BaseHandler` (`:862-884`) to get `_t` and `_send_message`. Several `_t(...)` calls pass no `user_id`, for example
   `action_cancelled`.
6. **Maintainability: dead code and stale comments.** `_start_edit_supplier_input` (`:845`) is never called. Seven
   `_start_*_input` methods are one-line wrappers around `handle_input_prompts`. "Phase 3 Batch A–G" comments describe
   a migration that is finished.
7. **Risk: errors are returned to the caller.** `handle_callback_query` returns `{"status": "error", "error": str(e)}`
   (`:751`). It isn't shown to users now, but the message text of an exception can hold data.

### `src/handlers/customer/info_commands.py`: one 290-line function and 19% coverage

1. **Maintainability: `handle_list_offers` has a complexity of 51.** It is 290 lines (`info_commands.py:283-572`) with
   seven `show_*` flags, three nearly identical branches (sold out, admin, customer) that each paginate, add a title,
   format lines and build a keyboard, and an unreachable `_send_message` at the end (`:571-572`). It is the
   customer-facing entry point of the bot, and it is barely tested: most of the file's 319 uncovered statements are
   here.
2. **Bug: offer names go into HTML messages unescaped.** `_format_offer_line` (`:144-163`) and `_send_offer_view`
   (`:718-734`) put `offer.name` (and, in the detail view, the supplier name) straight into `parse_mode="HTML"`
   messages. Offers are entered by the admin, so this isn't an injection risk. But a name like `Bier & Co` makes
   Telegram reject the whole message, and the offer list then doesn't appear at all. The group announcement already
   escapes the name. The description is different: it is HTML on purpose (Telegram formatting converted to HTML and
   validated when the admin enters it), so it must stay unescaped. **Fixed** in step 1.
3. **Bug: English-speaking customers get Dutch.** Of the `_t` calls in this file, 41 pass no `user_id`, so they always
   use Dutch. Most are admin texts, where Dutch is the default anyway. But `welcome_ubbc`, `help_general`,
   `help_orders`, `active_offers_customer`, `offer_not_found`, `offer_not_available`, `invalid_offer_id` and the order
   buttons are what customers see. **Fixed** in step 1: every call in the file passes the user.
4. **Bug: "Page" is hard-coded.** `f" - Page {page}/{total_pages}"` appears four times (`:336, :452, :462, :552`),
   in English, in an otherwise translated message. **Fixed** in step 1 with the existing `page_indicator` key.
5. **Maintainability: admin features in a customer handler.** The admin offer overview, the offer edit interface
   (`_show_edit_interface`), draft preview and publish buttons, and "view as user" are all in
   `handlers/customer/`. "View as user" works by passing a fake user ID, `999999` (`:631`).
6. **Maintainability: smaller problems.**
   - `_get_section_help` is a ten-branch `if` chain over a fixed mapping, and the admin section list is written out
     three times (`:79`, `:98-105`, `:114`).
   - `handle_start` creates a second `logger` that hides the module one (`:25-27`), and `handle_privacy` imports `os`
     inside the function.
   - `handle_help` formats the text twice (`:62` and `:68`): `_t` already fills in `bot_username`.
   - `_get_offer_capacity_info` has a `user_id` parameter it says it doesn't use, and filters on the strings
     `"pending"` and `"ordered"` instead of `OrderStatus`.
   - `handle_list_my_orders` builds a `BaseOrderHandler` to call its private `_show_customer_orders` (`:586-589`).
   - The presign-then-send logic for images is written out twice in `_send_offer_view` (`:677-703`).

### `src/services/database.py`: a facade that leaks around its repositories

The repositories exist and do the real work. The facade still does some of it too.

1. **Bug (latent): two scans read only the first page.** `get_suppliers_with_boxes_by_status` and
   `get_offers_by_supplier_and_box_status` (`database.py:417`, `:451`) call `boxes_table.scan(...)` once and don't
   follow `LastEvaluatedKey`. Once the boxes table is larger than 1 MB, the delivery workflow misses suppliers and
   offers, with no error. The order-history queries had the same bug and were fixed recently (commit `99f05d4`).
2. **Maintainability: eleven legacy table handles.** `__init__` still opens a handle for every table (`:46-57`)
   "to be removed". Only `boxes_table` (the two scans above) and `offers_table` (`delete_offer`, which also bypasses
   `OfferRepository` and its cache handling) are used.
3. **Risk: N+1 reads.** The supplier and offer lookups call `get_offer` per offer ID and `get_supplier_by_name` per
   name. `get_boxes_by_offer_with_orders` and `get_boxes_by_offer_with_order_status` read orders per box.
   `get_orders_by_customer_and_offer` reads every order of the offer to keep one customer's. The box-status and
   order-status variants are also copies of each other (`:413-568`).
4. **Maintainability: business rules in the data layer.** Audit logging (`AuditService(self)`, imported inside four
   methods) is triggered from `create_order`, `create_order_with_box_increment`, `update_order` and
   `batch_update_order_status`. So the data layer depends on a service that depends on the data layer.
   `create_order_with_box_increment` (`:169-237`) builds a raw low-level transaction with its own `boto3.client`,
   which belongs in `OrderRepository`.
5. **Risk: extra reads per write.** `update_order` reads the order before and after the update (`:292`, `:301`), and
   `cancel_order`, `adjust_order_price` and `mark_order_paid` each read it once more first (`:618`, `:632`, `:645`). A
   payment is three reads and a write.
6. **Maintainability: private methods are passed through.** `_list_offers_uncached`,
   `_get_customer_by_telegram_id_uncached` and `_get_customers_by_status_uncached` exist only so the caches can reach
   the repositories through the facade. `_serialize_datetime` and `_prepare_item` here are unused (the repositories
   have their own).
7. **Maintainability: S3 in the database service.** `upload_image_to_s3`, `get_presigned_url` and
   `delete_offer_images` have nothing to do with DynamoDB.

### Across the four files

- **No shared Telegram client.** This is the biggest single source of duplication (see `base_handler.py` finding 1),
  and it is why `CallbackHandler` and `InfoCommands` build extra handlers just to send messages.
- **Untyped dict results everywhere.** Handlers return `{"status": "..."}` with free-form strings, and Telegram calls
  return dicts with keys that differ per method (`success`, `message_id`, `message_ids`, `not_found`, `gone`,
  `skipped_guest`). A typo in a status string fails silently.
- **Broad `except Exception` with logging and a default return.** This keeps the webhook alive, which is right at the
  top. But in the data layer it turns a DynamoDB error into "no results", which is what the reporting code had to work
  around with `strict=True`.

## Refactoring plan

Each step is a separate change that can be deployed on its own. The order puts the bug fixes and the steps that make
later steps cheaper first. "Tests" says what must exist before or with the change. The dispatch tests
(`test_command_dispatch.py`, `test_callback_dispatch.py`) must stay green throughout: they are the safety net for any
routing change.

### Step 1: fix the bugs (small and independent)

- Escape `offer.name` (not the description, which is HTML) in `info_commands.py`, and pass `user_id` to the
  customer-facing `_t` calls there. Replace the hard-coded "Page" with a translation key (in `nl.json` and `en.json`).
- Make the two box scans in `database.py` follow `LastEvaluatedKey`, or better, move them into `BoxRepository` as a
  paginated `get_boxes_by_status` (a GSI on `status`, if one exists, avoids the scan altogether).
- Translate the "Enter reason" placeholder, and create the cancellation-reason context through
  `EditContextManager`.
- Make `_t` catch `KeyError`/`IndexError`/`ValueError` from `format`, log the key (not the parameters), and return the
  unformatted text. Add a test that formats every translation with dummy parameters, so a broken placeholder fails in
  CI instead of in production.

Tests: an offer named `Bier & Co <b>` in the list and in the detail view; an English customer sees English in
`/start` and `/list_offers`; a boxes scan that returns two pages.

### Step 2: extract a `TelegramClient`

Create `services/telegram_client.py` with one private `_call(method, payload, files=None)` that builds the URL,
checks the token, posts with the timeout, and turns the response into a small result type. Add one public method per
Bot API method used: `send_message`, `edit_message_text`, `edit_reply_markup`, `delete_message`, `answer_callback`,
`set_reaction`, `send_photo`, `send_media_group`, `send_document`, `get_me` and `get_file`.

Put the delivery rules in one place, in front of the send methods: the guest skip, the production group block with
`force_group`, and the `TEST - ` prefix. Then decide once whether edits and documents follow them. Today they don't,
and probably should.

`BaseHandler` keeps its `_send_message` etc. as thin delegates at first, so the 21 subclasses don't change. Later, the
callers can be moved over one by one. `CallbackHandler`, `MediaHandler`, `ImportHandler` and `message_sender.py` use
the client directly, which removes the extra `BaseHandler` in `CallbackHandler`.

Tests: one test file for the client with a mocked `requests.post`, covering the token check, the three delivery
rules and the error parsing (`not_found`, `gone`, "message is not modified"). The existing handler tests that patch
`_send_message` keep working.

### Step 3: extract a `Translator`

Move `_load_translations` and `_t` into `services/translator.py`, with a module-level cache (one load per container,
like the Telegram token). It looks up the user's language through `db.get_customer_by_telegram_id`, which is already
cached by `UserCache`. `BaseHandler._t` becomes a one-line delegate. This also gives `EditContextManager`, the
validator and the callback handler one shared translator instead of each holding a handler's `_t`.

### Step 4: split `InfoCommands`

- Move the admin parts to `handlers/admin/offer/overview.py`: the admin branch of `handle_list_offers`,
  `_show_edit_interface`, and the draft and publish buttons. `InfoCommands` keeps the customer views, and the command
  table points `/list_offers` at a small dispatcher that picks the admin or customer view.
- Replace the seven flags with data: a mapping from filter word to the statuses it shows, in display order. Then the
  admin overview is "group by status, paginate, add headers, format" in about 40 lines. That also makes the
  unreachable code at the end disappear.
- Move offer-line formatting and the offer keyboards into `services/offer_message_builder.py`, which already builds
  the group announcement. Then the announcement, the list and the detail view format offers the same way, with
  escaping in one place.
- Replace the fake user ID `999999` with an explicit `as_customer=True` parameter.
- Turn `_get_section_help` and the three section lists into one `HELP_SECTIONS` mapping (section → translation key,
  admin only yes/no).

Tests first: `info_commands.py` is at 19% coverage. Before splitting, add tests for each `/list_offers` filter (none,
`all`, `draft`, `active`, `import`, `completed`, `inactive`, `archived`, `soldout`, `user`, `help`), as admin and as
customer, with pagination. Then the split must not change any of their outputs.

### Step 5: declare callbacks as data

Turn the ~60 `router.register(pattern, lambda ...)` calls into a table, like `COMMAND_ROUTES` for commands:

```python
CallbackRoute(
    r"^order_(\d+)_(\d+)$",
    "customer_order",
    "handle_create_order",
    args=(INT, INT),
    chat="reply",
    customer=True,
    keep_keyboard=True,
)
```

- **`customer=True`** marks the routes customers may use, and `CUSTOMER_CALLBACK_PATTERN` is generated from them. The
  allowlist and the routes then can't drift apart. Everything without the flag stays admin-only, as now.
- **`keep_keyboard`** (or a `after=` policy such as "keep", "remove" or "delete message") replaces
  `_should_remove_keyboard` and the `process_payment_` special case.
- **Handler and method are named as strings, like in `COMMAND_ROUTES`.** A test checks that every named method exists
  and is public. That forces the private calls in finding 2 to become public methods on their handlers (for example
  `OfferCommands.audit_fill_boxes`), and a rename then fails a test instead of a button.
- **Order still matters (first match wins).** Keep the table in the same order as the current registrations, and
  generate the catch-all routes (`^admin`, `^cmd`, `^edit_`, `^page_`, `^wd_`, `^lc_`) from the table's prefixes.

Remove the dead `_start_edit_supplier_input`, the `_start_*_input` wrappers (the table can name
`handle_input_prompts` with a fixed argument), and the "Phase 3" comments.

Tests: `test_callback_dispatch.py` already taps every button as admin, as an approved customer and as a stranger.
Add a test that `CUSTOMER_CALLBACK_PATTERN` (now generated) matches exactly the routes marked `customer=True`.

### Step 6: shrink the database facade

- Delete the eleven legacy table handles once step 1 has moved the box scans. Move `delete_offer` to
  `OfferRepository`, where it invalidates the cache like the other offer writes.
- Move the order+box transaction into `OrderRepository`, and audit logging out of the data layer. Either a small
  `OrderService` (create, update, cancel, mark paid, each doing the write and then the audit), or audit hooks the
  repository calls. Then `database.py` has no `AuditService` imports, and `update_order` no longer needs to read the
  order twice (the service already has it).
- Merge the box-status and order-status supplier/offer lookups into two functions that take a set of offer IDs, and
  read the offers once (`list_offers` is cached) instead of per ID.
- Move the S3 methods to an `ImageStore` in `services/`.
- Let the caches call the repositories directly, and drop the `_..._uncached` pass-throughs and the unused
  `_serialize_datetime`/`_prepare_item`.

The facade then contains only one-line delegates. At that point it is worth deciding whether to keep it (one object
to pass around and mock) or let handlers depend on the repositories they use. Keeping it is the cheaper choice. The
tests mock `db` everywhere, and that mock is what keeps the handler tests short.

Tests: the existing repository tests (moto) cover the moved code. Add one for `delete_offer` invalidating the offer
cache, and one for a paid order writing exactly one `PAYMENT_RECEIVED` event through the new path.

### Step 7: move offer-message sync out of `BaseHandler`

Move `sync_offer_messages`, `_build_offer_message`, `_edit_tracked_message`, `_sync_subscriber_messages_async` and
`_check_offer_status_after_change` to `services/offer_message_sync.py`. It depends on the `TelegramClient` (step 2),
the translator (step 3) and the database. The handlers that call it get it injected, like `box_status_manager` and
`export_expiry` today. Remove `DecimalEncoder` and the repeated imports, and pass the environment in instead of
reading `ENVIRONMENT`.

After steps 2, 3 and 7, `BaseHandler` is what its name says: shared helpers for command handlers (admin check,
escaping, customer names, argument validation), at roughly 150 lines.

### Later: typed results

Once the Telegram client returns a small dataclass instead of a dict, the handler results can follow. An `enum` of
statuses, or at least constants, would catch typos in the status strings that the dispatch tests compare against.
That change is wide but mechanical, so it is best done file by file when a file is touched anyway.

## Expected result

| File                  | Now | After             | What moves out                                                                     |
|-----------------------|----:|------------------:|------------------------------------------------------------------------------------|
| `base_handler.py`     | 642 |              ~150 | Telegram client, translator, offer-message sync                                    |
| `callback_handler.py` | 903 | ~250 + route table | Lambdas become table rows; Telegram calls go to the client                        |
| `info_commands.py`    | 775 |              ~300 | Admin overview and edit interface; offer formatting goes to `OfferMessageBuilder` |
| `database.py`         | 690 |              ~350 | Legacy tables, transaction, audit, S3, duplicate lookups                           |

Line counts are estimates. The more useful measures are that `handle_list_offers` drops from complexity 51 to below
10, that `info_commands.py` rises from 19% coverage, and that there is one place each for the Telegram delivery rules,
the translations and the customer callback allowlist.
