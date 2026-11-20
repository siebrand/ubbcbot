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
  → `_execute_cancel` → `cancel_order`). `cancel_order` sets the status without a condition and returns True for an
  order that was already cancelled; `_execute_cancel` then takes the quantity off the box again. Only the
  `/cancel_order <full id>` path checks the status first; the confirmation button and the reason reply do not, so an
  old confirmation tapped again (or two admins' taps, or a retried webhook) leaves the box counting fewer units than
  its orders hold, and the box overbooks. Fix: cancel on condition that the order still has a status that may be
  cancelled, and change the box only when the cancel happened; better, the status and the box count in one
  transaction. Test: cancel the same order twice → the box loses its quantity once, the second answer says it is
  already cancelled.
  Done: `_execute_cancel` now uses `DynamoDBService.cancel_order_with_box` (`OrderRepository.cancel_with_box`): the
  order's status and the box count in one transaction, the order on condition of the status, box and quantity it was
  read with (and not cancelled), the box on condition that it holds the units. A rejected cancel reads the order
  again and says "already cancelled" (`already_cancelled`) or "failed". The customer is told once. The status
  follow-up is `BoxStatusManager.update_box_status_after_cancellation`. Found: `DynamoDBService.update_order`
  ignores its `admin_id` and `reason` arguments, so the reason given for a cancel is only in the customer's message;
  `/cancel_offer`, the wholesale plan and the wholesaler delivery still use the unconditional `cancel_order` (A5, B3).
  Tests: `tests/test_cancel_order_flow.py::TestAnOrderIsCancelledOnce`.
- [x] **A2. Cancelling a delivered order reopens a delivered box** (`_execute_cancel`,
  `update_box_after_order_cancellation`). `/cancel_order <id>` accepts an order in any status but `cancelled`: also
  `ready_for_labeling` … `awaiting_payment` and `completed`. The units go back to the box and the box is set to
  `open` whenever it is not `ordered`, so a `delivered` box becomes `open` and takes new orders for units that were
  delivered long ago; the offer can come back to life. The credit used for an order awaiting payment (audit 5, A2)
  is lost with it, and the payment link of the batch keeps asking for it. Fix: decide what cancelling a delivered
  order means (refuse it, or cancel without touching the box and give the applied credit back), and never reopen a
  `delivered` box. Test: cancel an order awaiting payment with credit applied → the box stays `delivered`, the credit
  is not lost.
  Done: decision: refuse it. Only a `pending` or `ordered` order is cancelled. `ACTIVE_ORDER_STATUSES` already said
  so ("an order that still takes room in a box and can be cancelled"), and the per-customer cancel list followed
  it; only the id paths and the reason reply ignored it. A delivered order has been labeled for, charged or paid, so
  the money (credit, payment link) would need undoing as well. For a customer who does not pick up, the admin can
  still give credit. `BaseHandler._refuse_cancel` is the one check, in `_execute_cancel` (every path ends there) and
  before the confirmation of the full and the partial id (`order_cannot_be_cancelled`, with the translated status).
  `ACTIVE_ORDER_STATUSES` moved to `models/entities.py` so that `base_handler` can use it. After units leave a box,
  its status only goes from `full` to `open` (`update_box_status_after_cancellation` and
  `update_box_after_order_cancellation`): `ordered` and `delivered` boxes are never reopened. Tests:
  `tests/test_cancel_order_flow.py::TestADeliveredOrderIsNotCancelled`.
- [x] **A3. `/edit_order` status has no guards, and the box does not follow** (`_apply_status_change`). Any status
  can be set on any order ("no guards" in the docstring). Setting `cancelled` keeps the units in the box (the box is
  full of nothing); setting a cancelled order back to `pending` or `ordered` puts units in a box that no longer has
  room for them (overbooked); setting `awaiting_payment` skips the credit and the payment link (audit 5), setting it
  back from `awaiting_payment` keeps the credit applied. Fix: crossing `cancelled` changes the box like a cancel or a
  placement (capacity-guarded, one transaction with the status), or offer only the transitions that are safe; and
  keep the money consistent. Test: edit a pending order to cancelled and back → the box count follows; back into a
  full box is refused.
  Done: decision: offer only the safe transitions (`OrderEditing._status_options(order)`, also checked again when
  the status is applied). The statuses from `pending` to `labeling_completed` (`CORRECTABLE_STATUSES`: the units are
  in the box, no money involved yet) may be corrected into one another. A pending or ordered order may be set to
  `cancelled`, which is a cancel (`cancel_order_with_box`, one transaction with the box, as A1/A2). A cancelled order
  is not brought back: its room may have gone to other orders, and placing a new order (`/order_for`) checks the
  capacity and the approval. `awaiting_payment` is not set by hand: only the delivery overview asks for a payment,
  with the credit and the payment link. An order awaiting payment may only be marked paid (`completed`, keeping its
  credit), and a paid order keeps its status. Every other change is written with `batch_update_order_status`
  on condition of the status that was read (`from_status`), so an order the delivery overview changed in between is
  not overwritten, and a payment still records its event. When nothing may be set, the screen says why
  (`edit_order_status_not_allowed`). Found: a cancel through `/edit_order` does not tell the customer (as before);
  `/cancel_order` does. Tests: `tests/test_edit_order_changes.py::TestTheStatusEditKeepsTheBoxRight`.
- [ ] **A4. Moving an order to another box is three writes, and the last has no rollback**
  (`_apply_box_change`). The new box is incremented, the old one decremented, then the order is updated; when the
  order update fails, both boxes have changed and the order is still in the old one. The move also takes no notice of
  the order's status (an order already delivered can be moved into an open box) or of the box's (`ordered` boxes are
  offered, so a pending order can be moved into a box that was already ordered from the wholesaler). Fix: one
  transaction (the order's `box_id` on condition of its old box and status, the two box counts with their capacity
  conditions); only orders and boxes for which the move makes sense. Test: a failing order update leaves both boxes
  as they were.
- [ ] **A5. The wholesale plan moves orders without a condition** (`_apply_wholesale_plan`). The plan is read, then
  every order in it is set to `ordered` (or reduced) unconditionally: an order cancelled by the admin while the plan
  runs (or between the plan screen and the confirmation) is set back to `ordered` and charged later; the reduced
  quantity is written over whatever is there. Same pattern as audit 5, A4. Fix: each write on condition of the
  status (and quantity) the plan read; an order that changed is left out and named. Test: an order cancelled after the
  plan was read stays cancelled and its units are not counted twice.

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
