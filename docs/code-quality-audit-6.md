# Code quality audit 6: where an order changes after it is placed

Status: **open** (2026-11-20). Follows audit 5 (where the money is collected), which is done. Audit 5 followed an order
from the delivery overview to its payment; this one follows what can happen to an order on the way: the admin cancels
it, edits its box, price or status, or the wholesale plan cuts it. Each of those changes the order and the box it
takes room in, and some of them the money. Same priorities as before:

- **High**: wrong behaviour, a security or privacy risk, money or stock that comes out wrong.
- **Medium**: a structural problem with a clear payoff (non-atomic writes, duplication, text that bypasses the
  translations).

Every fix comes with a test that fails before it; every refactor with a test that pins the behaviour first. Code that
touches capacity or credit uses DynamoDB conditions or transactions (CLAUDE.md, Gotchas). The customer-name matching
is fuzzy on purpose, also in the CSV import (owner, 2026-11-20): do not make it exact.

## Scope

| Area                | Files                                                                                                                                                      |
|---------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Cancelling an order | `src/handlers/admin/order/order_cancellation.py`, `src/handlers/base_handler.py` (`_execute_cancel`), `src/services/database.py` (`cancel_order`)          |
| Editing an order    | `src/handlers/admin/order/order_editing.py` (`/edit_order`: box, unit price, status)                                                                       |
| Box occupancy       | `src/services/box_status_manager.py` (`update_box_after_order_placement`/`_cancellation`), `src/repositories/box_repository.py` (`increment_box_quantity`) |
| The wholesale plan  | `src/handlers/admin/offer/management.py` (`_apply_wholesale_plan`, `/cancel_offer`)                                                                        |
| Texts               | the order handlers above (`user_id=None`, `_t` without a reader)                                                                                           |

## High priority

- [x] **A1. An order can be cancelled twice, and gives its units back twice** (`handle_confirm_cancel_with_reason`
  → `_execute_cancel` → `cancel_order`).
- [x] **A2. Cancelling a delivered order reopens a delivered box** (`_execute_cancel`,
  `update_box_after_order_cancellation`).
- [x] **A3. `/edit_order` status has no guards, and the box does not follow** (`_apply_status_change`).
- [x] **A4. Moving an order to another box is three writes, and the last has no rollback**
  (`_apply_box_change`).
- [x] **A5. The wholesale plan moves orders without a condition** (`_apply_wholesale_plan`).

## Medium priority

- [ ] **B1. The box status after a quantity change is decided from a stale read**
  (`update_box_after_order_placement`/`_cancellation`). The status (`full`/`open`) is computed from the box read
  before the atomic increment plus this change; a concurrent placement or cancel in between makes it wrong (a full
  box left `open`, an open one `full`), and the status write is unconditional. Fix: take the quantity from the
  increment's `UpdateItem` (`ReturnValues="UPDATED_NEW"`) and write the status on condition of it (and never from
  `delivered`).
- [ ] **B2. A unit price edit ignores what has happened to the order** (`_apply_unit_price_change`). The price of an
  order awaiting payment can change after the overview asked for it (with `credit_applied` possibly above the new
  total, so `amount_due` goes negative), and the price of a completed order after the payment event was recorded.
  Fix: decide which statuses may get a new price; for one awaiting payment, keep the credit within the new total (and
  tell the admin the customer was asked for another amount).
- [ ] **B3. `/cancel_offer` cancels orders one by one without their boxes or a condition** (`handle_cancel_offer`).
  Check what it does with the boxes and the credit of orders already awaiting payment (same questions as A1, A2);
  pin it first.
- [ ] **B4. The order handlers translate without a reader** (left by audit 5, B4). `order_editing.py` (`user_id=None`
  and `self._t(..., None, ...)`), `order_cancellation.py` (`self._t("order_not_found")`, `self._t("box_not_found")`),
  `order_placement.py`, `order_viewing.py`, `wholesale_delivery_handler.py`, `labeling_commands.py`: an English admin
  gets Dutch. Fix as in audit 5: the admin (or the private chat) as reader; extend
  `tests/test_admin_payment_screens_in_english.py`'s marking approach to these screens.

## Order of work

Stock and money first, each with a test that fails before the fix: A1 (the double cancel), A2 (cancelling what was
delivered, which decides what A3 may allow), A3, A4, A5. Then B1 (the status from the increment), B3 (pin first),
B2, and last the texts: B4. A2, A3 and B2 each need a decision about what the admin may do: pick one and say why in
the note.
