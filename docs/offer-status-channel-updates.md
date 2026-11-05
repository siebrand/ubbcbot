# Updating offer status and content in the channel and subscriber messages

Status: **complete.** Steps 1–3 committed (`0bd82e2`, `fcf7ccc`, `317b7bc`);
Steps 4–5 committed (`ffaaa6e`); Step 6 (changelog + README) done. See
"Implementation status & remaining work" for the per-step record.

## Goal

When an offer changes — either its **status** or its **content** — re-render the
already-sent announcements so they reflect reality.

**Status changes** (icon + order buttons):

- `active → sold_out` — mark sold out, remove the order buttons.
- `active → cancelled` (and `sold_out → cancelled`) — mark cancelled, remove the
  order buttons.
- `sold_out → active` (available again) — clear the sold-out marker, re-add the
  order buttons.

**Content changes** (title/body text) within the tracking window:

- **name** changed (`/update_offer_name`)
- **price** changed (`/update_offer_price`)
- **description** changed (`/update_offer_description`)

In all cases the message is re-rendered from the **current** offer (current name,
price, description) **plus** the current status icon/buttons — i.e. one builder
produces the whole message, and any trigger (status or content) re-runs it. A
price edit on a sold-out offer therefore keeps the 🔴 marker and the
buttons-removed state while updating the price.

Updates apply to **both** the group/channel announcement and the individual
subscriber DMs, with the **group updated first** (one cheap edit) and the
subscriber DMs trickling afterward.

## Key finding / prerequisite

The `notifications` table and `NotificationMessage` entity (`notification_id`,
`offer_id`, `chat_id`, `message_id`, `created_at`) already exist, with an
`offer-index` GSI, and `create_notification_message` /
`get_notification_messages_by_offer` / `delete_notification_message` are wired
through to the repository. **But `create_notification_message` is never called**
— no message ids are captured today. The dormant sold-out cleanup
(`_delete_offer_notifications`) therefore iterates an empty set.

So the linchpin of this feature is: **capture the message id of every
announcement we send** (group + each subscriber DM) at send time, keyed by
`offer_id`. Editing a Telegram message requires its `chat_id` + `message_id`.

### What to store, where, how long

Reuse the existing `notifications` table — its schema is already exactly right:

| Field | Use |
|---|---|
| `notification_id` | PK (uuid) |
| `offer_id` | GSI `offer-index` — look up all messages for an offer |
| `chat_id` | where the message lives (group id, or a subscriber's chat) |
| `message_id` | the Telegram message to edit |
| `created_at` | send time |

Add a **`ttl`** attribute (new) and enable DynamoDB TTL on the table, set to
**168 hours (7 days)** after `created_at` for **both** group and subscriber rows.
Because every message (group and DM) is edited rather than deleted, and may need
reverting on `sold_out → active`, all tracking rows must stay editable for the
same window. After expiry the row self-expires and that message is no longer
edited by the bot (a status change on a week-old offer is not worth chasing).

A **`kind`** attribute (`group` / `subscriber`) is still stored — not for a
different TTL, but to order the edits (group first) and trickle the subscriber
edits as a batch. Optionally store the **`message_kind`** (text vs photo) — see
"Message type" below.

## Message type analysis (what is actually editable)

From `notifications.py`, an announcement is sent as **two separate Telegram
messages**:

1. Zero or more **images** (`sendPhoto` for one, `sendMediaGroup` for several).
2. A **text message** (`sendMessage`) containing the title line, description,
   and the inline order buttons.

Telegram editing constraints:

- A media group's items cannot be text-edited; individual photo captions can be
  edited but these announcements put the text in a **separate message**, not a
  caption.
- The **text message** is a normal `sendMessage`, editable via
  `editMessageText` (text + inline keyboard together).

**Conclusion:** we only need to track and edit the **text message** of each
announcement. The images stay as-is. So at send time we capture the
`message_id` returned by the `sendMessage` call (group and each subscriber), not
the photo messages. `_send_message` must return/expose the sent `message_id`
(verify it does; if not, thread it through).

## Status identifier in the message

The group title line today is:

```
<b><a href="…view_offer_{id}">{id}</a>. {name} €{price}</b>
```

and the subscriber variant appends `  ({available}/{total})`.

Proposal: a **single status icon as the first character of the title line**,
before the offer id, so it is unmissable and language-neutral:

| State | Icon | Title line example |
|---|---|---|
| active | *(none)* | `12. Beer €4.50` |
| sold_out | 🔴 | `🔴 12. Beer €4.50 — UITVERKOCHT` |
| cancelled | ⛔ | `⛔ 12. Beer €4.50 — GEANNULEERD` |

Rationale for a leading icon: it is visible in Telegram's chat preview/truncated
view, needs no layout change, and reverts cleanly (removing the icon restores
the active look). A short localized suffix word (UITVERKOCHT / GEANNULEERD, or
SOLD OUT / CANCELLED) is added after the title for screen-reader/clarity; the
group always uses Dutch per the i18n rules. For `sold_out → active` the icon and
suffix are removed, returning the title to its original form.

## Buttons

- `sold_out` / `cancelled`: edit the message with **no `reply_markup`** (order
  buttons removed), so no one can still tap "order".
- `active` (available again): edit with the order buttons **re-added** (the same
  `order_{offer_id}_1 / _2` keyboard used at announce time).

## Triggers

The sync runs **automatically** wherever the offer changes.

Status transitions:

- The automatic `active → sold_out` when the last unit is ordered
  (`update_offer_status_after_change` / `_check_offer_status_after_change`).
- `→ cancelled` via `/cancel_offer`.
- `sold_out → active` when capacity reopens (e.g. an order cancelled, a box
  added).
- **`/offer_status`** — but only for the `active → sold_out` case. This is the
  manual path the admin uses when a bug prevented the automatic transition; it
  must trigger the same channel/subscriber update. Other `/offer_status`
  transitions do not trigger message updates.

Content changes (re-render title/body from the current offer, keeping the
current status icon/buttons) — hook in after the successful `db.update_offer(...)`
in each handler (`offer/editing.py`):

- `/update_offer_name`
- `/update_offer_price`
- `/update_offer_description`

These three handlers are the **only** places name/price/description are mutated
(verified: the other `db.update_offer` call sites only change status/images). The
`/view_offer` edit menu has no separate path — its buttons open a text prompt and
`bot_service` dispatches the reply to these same three handlers — so hooking the
sync here covers both the slash commands and the edit-menu flow.

Implementation: a single `sync_offer_messages(offer_id)` entry point called from
each of those sites. It derives the offer's current state and content itself (no
caller needs to pass them), looks up the tracked messages via `offer-index`,
edits the group message first, then trickles the subscriber DMs. Because it
always renders from the current offer + current status, it is correct whether the
trigger was a status change or a content edit.

## Flow (per change)

1. Offer status or content changes (any trigger above).
2. `sync_offer_messages(offer_id)`:
   a. `get_notification_messages_by_offer(offer_id)` → tracked (chat_id,
      message_id) rows (group first, then DMs).
   b. Rebuild the title line with the appropriate icon/suffix and the correct
      keyboard (buttons for active, none for sold_out/cancelled).
   c. `editMessageText` the **group** message.
   d. Trickle `editMessageText` over the subscriber DM messages (best-effort;
      log and continue on individual failures — a subscriber may have deleted
      the DM).
3. Rows that have expired (TTL) or whose edit returns "message not found" are
   skipped (and may be pruned).

## Where it runs (Lambda topology)

The sync mirrors how announcements are already sent, so it reuses existing
infrastructure rather than adding a Lambda:

- **WebhookHandler** (the main bot Lambda) is where every trigger originates — a
  status transition (ordering the last unit, `/cancel_offer`, `/offer_status`,
  box changes) or a content edit (`/update_offer_*`). It runs
  `sync_offer_messages(offer_id)`.
- The **group message edit is one API call** and is always done **inline in
  WebhookHandler, first** — it is cheap and is the most important surface, so it
  must not depend on an async hop.
- The **subscriber DM edits** reuse the exact pattern the announce path already
  uses (`notifications.py`):
  - **≤ 10 subscriber messages:** edit them **inline** in WebhookHandler (fast
    enough, no cold-start/second-hop cost).
  - **> 10:** hand off to the **NotificationSender** Lambda via async
    `lambda_client.invoke(InvocationType="Event", ...)`. NotificationSender
    already has the right shape for this — a 300s timeout and batching with small
    sleeps between batches to stay under Telegram's rate limits. It gets a new
    entry mode (e.g. `{"action": "sync_offer_messages", "offer_id": ...}`) that
    loads the tracked `kind == subscriber` rows and edits each message, batched,
    instead of (or alongside) its existing bulk-send mode.

So: **WebhookHandler** always does the group edit (and small DM batches);
**NotificationSender** does large DM batches asynchronously. No new Lambda, no
template change beyond the `notifications` table TTL/`kind` attributes already
listed.

## Rate limiting / failure handling

- Group edit is a single call — always inline and first.
- Subscriber edits trickle via the ≤10-inline / >10-async split above, so large
  subscriber counts neither block the webhook response nor hit Telegram rate
  limits (NotificationSender batches with `time.sleep` between batches, exactly
  as the bulk-send path does today).
- Per-message failures are logged and skipped; one bad/edited-away DM never
  aborts the batch. Rows whose edit returns "message not found" (or whose 168h
  TTL has expired) are skipped and may be pruned via `delete_notification_message`.
- Editing is idempotent: re-running a sync re-applies the same title/keyboard, so
  a retry or a double-trigger is harmless.

## Implementation status & remaining work (TDD, atomic commits)

### Done

- **Step 1 — remove the incomplete delete feature.** Commit `0bd82e2`.
  Removed `base_handler._delete_offer_notifications` (and the sold-out delete call
  in `_check_offer_status_after_change`, which now only recomputes status via
  `box_status_manager`), and `offer/management.py._cleanup_offer_notifications`
  plus its call in the `/cancel_offer` path. Tests in
  `tests/handlers/admin/order/test_base_order_handler.py` rewritten. The
  `notifications` table, `NotificationMessage` entity, and repo CRUD were kept.
- **Step 2 — message builder.** Commit `fcf7ccc`.
  `src/services/offer_message_builder.py` — `OfferMessageBuilder(bot_username,
  translate).build(offer, cancelled=False) -> (text, reply_markup)`. active → no
  icon + order buttons; sold_out → 🔴 + `status_sold_out` suffix + no buttons;
  cancelled → ⛔ + `status_cancelled` suffix + no buttons. Name is HTML-escaped.
  Pure; tested in `tests/test_offer_message_builder.py`.
- **Step 3 — capture message ids (+ TTL/kind, template).** (pending commit)
  Added `kind` (`"group"`/`"subscriber"`, default `"group"`) and `ttl`
  (`int | None`, computed to `created_at + 168h` in `__post_init__`, tolerant of a
  string `created_at` for the DynamoDB round-trip) to `NotificationMessage`
  (`src/models/entities.py`). Enabled `TimeToLiveSpecification` on `ttl` for the
  `notifications` table (`template.yaml`); `kind`/`ttl` are non-key attributes so
  no `AttributeDefinitions`/conftest fixture change was needed. Capture is wired at
  every announce send site after a successful `_send_message`
  (`result["success"]`): group announcement in
  `offer/notifications.py._send_rich_offer_message` (only when `not preview`, via
  the new `_track_notification_message` helper, `kind="group"`); subscriber DMs in
  `_send_optimized_rich_message` and `_send_simple_offer_notification`
  (`kind="subscriber"`); and the bulk Lambda
  `notification_sender.py._send_notification_to_customer` (`kind="subscriber"`).
  Tests in `tests/handlers/admin/offer/test_notification_tracking.py` (group row,
  subscriber row, preview skipped, failed-send skipped, ttl ≈168h, string
  `created_at`). Full suite green (592 passed; the one collection error in
  `test_privacy.py` is a pre-existing missing `markdown` dependency, unrelated);
  `sam validate --lint` passes.

### Done (Steps 4–6)

- **Step 4 — `_edit_message_text` helper + `sync_offer_messages`.** Commit
  `ffaaa6e`. Added `BaseHandler._edit_message_text(chat_id, message_id, text,
  parse_mode=None, reply_markup=None) -> {"success", "not_found"}` (calls Telegram
  `editMessageText`; treats "message is not modified" as success and
  "message to edit not found" / "message can't be edited" / "chat not found" as
  `not_found`). Added `BaseHandler.sync_offer_messages(offer_id, cancelled=False)`:
  loads the offer, builds `(text, markup)` via `OfferMessageBuilder` (group
  language forced to Dutch), reads rows via `get_notification_messages_by_offer`,
  edits the group row(s) first, then subscriber rows (≤10 inline; >10 →
  `_sync_subscriber_messages_async`). `_edit_tracked_message` sends an **empty**
  keyboard (`{"inline_keyboard": []}`) when markup is None so sold_out/cancelled
  actually drop the order buttons, and prunes the row on `not_found`. Tested in
  `tests/handlers/admin/offer/test_offer_message_sync.py`.
- **Step 5 — wire triggers + NotificationSender async mode.** Commit `ffaaa6e`.
  `_check_offer_status_after_change` now captures the status returned by
  `box_status_manager.update_offer_status_after_change` and calls
  `sync_offer_messages` when it changed; the direct `box_status_manager` callers
  in `order_placement.py`, `order_cancellation.py`, `order_editing.py`, and
  `customer/order_commands.py` were routed through this wrapper.
  `/cancel_offer` (both the no-orders and confirmed paths in `management.py`) calls
  `sync_offer_messages(offer_id, cancelled=True)`; `/offer_status` calls it for the
  **soldout case only**; the three `offer/editing.py` content updaters call it
  after a successful `db.update_offer`. `notification_sender.lambda_handler`
  dispatches on `event["action"]`: `sync_offer_messages` →
  `NotificationSender.sync_subscriber_messages(offer, cancelled)` which edits only
  `kind == "subscriber"` rows in batches of 20 with `time.sleep(0.5)` between
  batches; the `cancelled` flag is threaded through the async payload. Routing
  tests in `tests/handlers/admin/offer/test_offer_sync_triggers.py` plus the
  updated `tests/handlers/admin/order/test_base_order_handler.py`.
- **Step 6 — user-facing docs.** Added a changelog entry
  (`src/handlers/customer/changelog_commands.py`, "Up to 2026-11-06") describing
  the live announcement updates, and rewrote the README "Notification Management"
  section (the old "delete on sold out / cancel" bullets, removed in Step 1, were
  replaced by the edit-in-place behaviour). This design doc is intentionally
  **not** committed.

Verification across the work: full suite 619 passed (the lone `test_privacy.py`
collection error is a pre-existing missing `markdown` dependency, unrelated);
`sam validate --lint` passes; the pre-commit ruff hook reformatted and the commits
contain the formatted result. ruff is not installed in this environment, so it was
run only via the commit hook, not standalone.

## Decision: edit everything, delete nothing

Both the group/channel message **and** the subscriber DMs are **edited** to carry
the status icon (and have buttons removed/re-added). **No message is ever
deleted.** `sold_out → active` reverts the icon and re-adds the buttons on every
message. This supersedes the earlier "delete subscriber DMs" idea.

Consequence for TTL: because subscriber DMs are now edited (not deleted) and may
need reverting on re-activation, their tracking must live as long as the group's.
**Use 168h (7 days) for both `group` and `subscriber` rows.** (The earlier
72h/168h split assumed DMs were deleted at sold_out and never touched again; that
no longer holds.) The `kind` attribute is still useful for group-first ordering
and for projecting the subscriber edits as a trickled batch.

## Removal of the incomplete delete feature

There is a half-built "delete offer notifications" feature that never worked (it
iterates an empty set because message ids are never stored). We are committing to
the edit approach, so this dead/incomplete code is **removed** to avoid a second,
conflicting behaviour.

**Remove:**

- `base_handler._delete_offer_notifications(offer_id)` — the delete loop.
- `base_handler._check_offer_status_after_change(offer_id)` — its only caller,
  which is itself **never called** from anywhere in the codebase (dead).
- `offer/management.py._cleanup_offer_notifications(offer_id)` and its call site
  in the `/cancel_offer` path (`management.py:496`). The cancelled-state message
  update is handled by `sync_offer_messages(offer_id)` instead (the offer is
  already `cancelled` at that point, so the sync renders the cancelled marker).
- `tests/handlers/admin/order/test_base_order_handler.py` cases that exercise
  `_check_offer_status_after_change` (they test the behaviour being removed).

**Keep (reused by the edit feature — not part of the delete feature):**

- The `notifications` DynamoDB table and the `NotificationMessage` entity.
- The repository CRUD `create_notification_message` /
  `get_notification_messages_by_offer` / `delete_notification_message` and their
  `database.py` wrappers. `create`/`get` are needed to store and look up message
  ids for editing. `delete_notification_message` is retained only for pruning
  rows whose Telegram message is gone (edit returns "message not found"); it is
  no longer used to implement a user-facing delete.
- `tests/test_repositories/test_notification_repository.py` — exercises the CRUD
  we keep.

**Sequencing:** remove the dead delete code in its own commit *before* building
the capture + `sync_offer_messages` edit path, so the tree never has both the
delete and edit behaviours wired at once.

## Open decision surfaced during design

Resolved: **edit all messages, delete none**; group and subscriber tracking both
expire at 168h. No open questions remain for behaviour; remaining work is the
implementation steps above.
