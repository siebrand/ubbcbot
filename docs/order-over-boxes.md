# Order what is left when a request is more than one box has room for

Status: **in progress** (2026-11-22). Item 5 of the planning of 2026-11-21 (decisions taken that day); the planning
file was lost, this is its text, with the decisions made while building it and the state of the work below.

Every item follows the project rules (CLAUDE.md): tests first, texts in `nl.json` and `en.json`, a new command in
`COMMAND_ROUTES` plus its row in `tests/test_command_dispatch.py`, the help text, `telegram-commands.json` and the
README together; conventional commits on `main`.

## Goal

A customer who asks for more than one box has room for gets what can be ordered, and is told plainly if that is
less than asked. Today they get "❌ Bestelling past niet in bestaande colli's. Bestellingen kunnen niet over
meerdere colli's verdeeld worden." (`order_too_large_for_remaining_space`), which is not their problem: there are only
X units left.

## Behaviour

- The requested quantity is spread over the boxes of the offer that have room, in this order, each group oldest
  first (by `created_at`):
  1. **delivered** boxes;
  2. **ordered** boxes;
  3. **open** boxes.

  An order stays in one box, so a request that spans boxes becomes one order per box. Example: 4 requested, 2 free in
  each of two boxes → two orders of 2.
- What is still left after the existing boxes goes into **as many new boxes as it needs**, each of the offer's box
  size, but only when the offer may get new boxes. That rule is unchanged: the offer is active or import, and **none
  of its boxes is ordered or delivered**. Example: box size 1, active offer without ordered or delivered boxes, 5
  requested → five new boxes of 1 and five orders of 1, each box full.
- An order never makes a box for an offer that has an ordered or delivered box. The only way to add room there is
  the admin's decision: `/create_box <offer_id>` adds an open box (it does so today, whatever the other boxes are),
  and orders then fill it as an open box, after the delivered and ordered boxes.
- When no new box may be made, the free units are ordered without asking first, and the customer is told: "Je
  bestelde 4, er konden er maar 2 worden besteld." With no free units at all: the sold-out message
  (`offer_sold_out_named`), and no order.
- One confirmation to the customer and one group announcement per request, with the total quantity and amount, not
  one per order.
- Every entry point behaves this way: the group order buttons, `/order`, the `view_offer` deep link and `/order_for`.
  With `/order_for`, the admin's confirmation says the same (ordered, and how many of the request could be ordered).

**No box-size limit:** today `execute_order` refuses a request larger than the box size
(`quantity_exceeds_box_size`); that check goes, and so does its text once nothing uses it. A request is then limited
by the order limit and, for an offer that may not get new boxes, by the free units in its boxes.

**Unchanged:** the order limit (`validate_order_limit`, 5 pending or ordered units per customer per offer) and the
duplicate-order check look at the request as a whole, before anything is written. So with the current limit a single
request is at most 5 units.

## Where

- `handlers/customer/order_commands.py`:
  - remove the `quantity > offer.wholesale_box_size` check from `execute_order`;
  - replace `_find_or_create_box` with a function that returns the allocation: a list of (existing box, units) in the
    order above, plus the new boxes needed for the rest (`ceil(rest / box size)`, the last one possibly not full);
  - `execute_order` writes the allocation, then does the follow-ups once: the FULL status of each box that reached
    its capacity, `_check_offer_status_after_change`, the confirmation;
  - `_create_and_assign_order` sets each order's status from its own box (delivered → ready for labeling, ordered →
    ordered, otherwise pending), as now;
  - `_send_order_confirmation` and the `/order_for` caller take the list of orders and the shortfall.
- `services/database.py` (and the order and box repositories): next to `create_order_with_box_increment`, one
  DynamoDB transaction for the whole request: the new boxes (created with their quantity already set), the orders,
  and the increments of the existing boxes, each with the condition that the box still has room (CLAUDE.md: capacity
  changes must not overbook). So a failed request leaves no empty new boxes behind. If a condition fails because
  someone else took the units in the meantime, read the boxes again and allocate once more; if that fails as well,
  `order_failed`. A transaction holds at most 100 items; with the order limit of 5 a request has at most 10.
- Remove `order_too_large_for_remaining_space` from both translation files once nothing uses it; new texts for the
  shortfall (customer and admin).

## Done when

- 4 requested, 2 free in each of two delivered boxes → two orders of 2, ready for labeling, one confirmation of 4.
- 4 requested, 2 free in one delivered box and no new box allowed → one order of 2 and the shortfall message.
- 0 free → the sold-out message, no order.
- An open offer with 3 of 6 in its box, 5 requested → 3 in the open box, 2 in a new box, one confirmation of 5.
- An active offer with box size 1 and no boxes, 5 requested → five boxes of 1, five orders of 1, one confirmation of
  5; 6 requested → the order limit message, nothing written.
- An offer with an old and a new delivered box with room, an ordered box with room and an older open box (made with
  `/create_box`): the delivered boxes are filled first (old, then new), then the ordered box, then the open box; no
  new box is made, the rest is the shortfall.
- Two requests for the last units at the same time never get more units than the boxes have.

**Tests:** each case above, against the moto database; each entry point (group button, `/order`, deep link,
`/order_for`); the race for the last units (the second transaction fails its condition and gets the rest, or the
sold-out message); the order limit and the duplicate check on a request that spans boxes; the group announcement is
sent once.

**Docs:** README (ordering), and the help text of `/order` and `/order_for` if they say an order must fit one box.

## Decisions made while building

- The allocation is a pure function of its own, `services/order_allocation.py` (`allocate`, `may_create_boxes`,
  `Allocation` with `placed` and `shortfall`), so the order of the boxes is tested without a database. A `full` box
  counts with the open boxes (it has no room anyway).
- The transaction is `OrderRepository.create_with_boxes` / `DynamoDBService.create_orders_in_boxes`; it records one
  `ORDER_CREATED` event per order after the commit. A new box is written `full` when the request fills it, else
  `open`; an existing box that reaches its capacity gets the conditional FULL write of audit 6, B1
  (`mark_box_full_if_at_capacity`), so an ordered or delivered box keeps its status.
- `execute_order` tries `ORDER_ATTEMPTS = 2` times (read, allocate, write). Results: `success` (also with a
  shortfall), `sold_out` (no room at all), `error` (the write kept failing: `order_failed`). For an order the admin
  places it returns the `orders` and the `shortfall`, and its own messages are in the admin's language.
- One confirmation per request (`order_placed_single` with all short order ids, the total units and amount, and the
  statuses once each), followed by the shortfall line. Texts: `order_shortfall` (customer), `order_for_shortfall`
  (admin, `/order_for`). `quantity_exceeds_box_size` and `order_too_large_for_remaining_space` are removed.
- `/order_for`: the customer's `admin_order_placed` and the group announcement have the placed total; the admin's
  confirmation adds `order_for_shortfall` when less could be ordered.

## State of the work

- Done and committed: the allocation (`2394117`), the transaction (`73b4965`).
- Written, not committed yet: `execute_order` on the allocation and the transaction, the confirmation, `/order_for`,
  the texts, and the tests in `tests/test_customer_order_flow.py` (`TestARequestOverSeveralBoxes` and the updated
  one-box tests), `tests/test_instant_offer_state.py` and `tests/test_html_escaping.py`. The full suite passes.
- To do: an `/order_for` test with a shortfall (`tests/test_order_for_flow.py`), a test through the group order
  button and the deep link, the README ordering section and the `/order` and `/order_for` help texts; then commit as
  `feat:`.
