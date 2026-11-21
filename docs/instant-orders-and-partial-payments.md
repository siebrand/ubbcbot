# Instant Orders and Partial Payments: Use Cases

Status: use cases agreed. The technical designs are in [instant-orders-design.md](instant-orders-design.md) and
[partial-payments-design.md](partial-payments-design.md).

This document gives the use cases for two features, in terms of the current system. It has no data model, handler or
table changes. Those are in the technical designs.

Wording rules: "must" is a requirement. "can" is an option. Each term in the glossary has one meaning only.

## Glossary

| Term | Meaning |
|------|---------|
| admin | The one user in `ADMIN_USER_ID`. |
| customer | A person with a customer record. A guest is a customer without Telegram. |
| offer | A beer product from one supplier, with a name and a price. Statuses: `draft`, `import`, `active`, `ordered`, `sold_out`, `completed`, `delivered`, `inactive`. |
| box | A wholesale box that holds units of one offer. Statuses: `open`, `full`, `ordered`, `delivered`. |
| order | The units that one customer takes from one offer. Statuses: `pending`, `ordered`, `received_partial_delayed`, `ready_for_labeling`, `labeling_completed`, `awaiting_payment`, `completed`, `cancelled`. |
| sold out | An offer has no free units. Offer status is `sold_out`. |
| full | A box has no free units. Box status is `full` or a later status. |
| instant offer | An offer that `/instant_order` creates, with one box. After it is created, it is an ordinary offer. |
| amount due | The order total minus the credit that the delivery overview applied. This is what the customer must pay. |
| open order | An order with status `awaiting_payment`. |
| paid | An order has status `completed` and a `PAYMENT_RECEIVED` event. |

## Current system

- An offer has a supplier and boxes. A box goes through `open`, `full`, `ordered`, `delivered`. An offer is
  `completed` only when it is `sold_out` and all its boxes are `delivered`.
- An order goes through `ordered`, `ready_for_labeling`, `labeling_completed`, `awaiting_payment`, `completed`.
  `/process_delivery` sets boxes and orders to delivered and `ready_for_labeling`. `/process_labeling` sets
  `labeling_completed`. `/send_delivery_overviews` sets `awaiting_payment`.
- The delivery overview applies the credit balance (or debt) of the customer once. The rest is the amount due.
- `/process_payment` marks all open orders of one customer as paid in one action. Each paid order writes one
  `PAYMENT_RECEIVED` event. The purchase reports add up these events.
- `/order_for` lets the admin order for a customer. A customer can order at most 5 units per offer.
- The bot announces an offer to the group and to subscribers when the offer is published. It edits the announcement in
  place when the offer is sold out or cancelled.

---

## Feature 1: Instant orders

### Purpose

The admin sells beer that is already in hand. One command creates the offer and the first order. The wholesale and
delivery steps are skipped.

### Command

`/instant_order <supplier> <offer name> <price> <customer> [box_size]`

- The supplier is the first parameter, as in `/create_offer`.
- Quotes can group a name that has spaces: `/instant_order "Supplier" "Offer name" 3.50 jan 4`. Without arguments, the
  command asks for each value in turn.
- The first order always has quantity 1. The command has no quantity parameter.
- Box size is 1 when it is missing. The box size must be 1 to 6.
- The command acts at once. It has no confirmation step.

### Customer matching

- The command uses the existing fuzzy customer matching, limited to customers with authorization status `approved`.
  Guests have this status, so the command can match them. Customers that are pending or rejected are never matched or
  suggested.
- `/order_for` must follow the same rule. Today it also matches pending and rejected customers. This is a bug, and its
  fix is part of this work. Other admin commands that match customers (for example `/approve_user`) keep their
  behavior, because they must find unapproved customers.
- No match: the bot shows an error. It creates nothing.
- More than one match: the bot shows a list. The admin picks one customer. The bot creates nothing before that.

### Use cases

**UC1.1 First order creates the offer.**
The admin runs the command. The bot creates the offer, one box, and the first order. The box gets status `delivered`.
The order gets status `ready_for_labeling`. It then follows `/process_labeling`, the delivery overview and payment as
usual. The admin and the customer both get a confirmation, as with `/order_for`.

**UC1.2 The first order fills the box.**
This happens when the box size is 1, which is the default. The offer is `sold_out` at once. The bot sends no
announcement and no subscriber notification. Nobody can order more. The offer becomes `completed` after labeling, as
other sold out offers do.

**UC1.3 The box has free units.**
The offer is `active`. The bot announces it to the group, in Dutch, with the order button. The announcement is the only
group message for the first order. The bot does not send a separate order message that names the customer, and it does
not notify subscribers. When the offer is sold out, the bot edits the announcement in place, as for regular offers.

**UC1.4 Later orders on an instant offer with free units.**
- The admin can use `/order_for <customer> <offer_id> [quantity]`. A customer can use `/order`, `/fomo` and
  `/list_offers`. This is possible until the offer is sold out.
- Each of these orders gets status `ready_for_labeling` at once, because the box is already `delivered`. It does not
  go through the wholesale steps.
- The usual confirmations apply to the customer and the admin. The bot also sends the group message, with the sold out
  notice when a customer takes the last unit.
- The 5-unit limit and the duplicate order confirmation apply to customers.

**UC1.5 Offer status.**
The offer status follows the same rules as for a regular offer: `active` while the box has free units, `sold_out` when
it has none, `completed` after labeling. `/view_offer`, `/list_boxes`, `/audit_offer` and the reports work for instant
offers as for other offers.

**UC1.6 Editing.**
The admin can change the name, price or description of an instant offer. When the offer has a group announcement, the
bot updates the announcement, as for regular offers.

**UC1.7 Cancelling an instant order.**
The existing cancel flow applies. The unit is free again. A `sold_out` offer becomes `active` again, and the group
announcement gets the order button back. The box stays `delivered`. The bot notifies the customer, as today.
The bot allows this while the order has status `ready_for_labeling`. This is a change: today it only allows `pending`
and `ordered` orders. It applies to every order in that status, not only to instant orders. From `labeling_completed`
onward the bot still refuses, because the delivery overview applies credit after that.

### Rules

- Only the admin can create an instant offer.
- The bot creates the offer with exactly one box. After that, the offer follows the same rules as every other offer.
- The bot does not notify subscribers when it creates an instant offer.
- The bot sends a group announcement only when the box has free units after the first order.
- Every `/instant_order` creates a separate offer, also with the same supplier, name and price.
- The prefix "TEST - " in the test environment and Dutch in group messages apply, as everywhere.

### Edge cases for the design

- The supplier is unknown or archived: the bot shows an error. It creates nothing.
- The price is not a positive number, or the box size is not a whole number from 1 to 6: the bot shows an error. It
  creates nothing.
- A step fails during creation: the bot must not leave an offer without its box or its order.

---

## Feature 2: Partial payments

### Purpose

A few customers do not pay quickly, so several deliveries stay unpaid. When such a customer pays for some of them, the
admin today must note off-system which orders are paid. `/process_payment` can only mark all open orders as paid. The
admin needs to register such a payment in the system.

### Principles

- A payment settles whole orders. The bot never part-pays an order.
- The feature does not use credit. Credit stays what it is today: money owed to the customer, applied once at the
  delivery overview. An unpaid order stays an open order until it is paid.
- The bot registers a payment per order, as today. Each paid order writes one `PAYMENT_RECEIVED` event with the amount
  due of that order. The purchase reports do not change.

### Use cases

**UC2.1 Register an amount received.**
In the payment flow for a customer, the admin enters the amount received. The bot selects the oldest set of open
orders whose amounts due add up to exactly that amount. It shows the selected orders with offer, date and amount. The
admin confirms with a button. The bot marks the orders as paid. The customer gets a confirmation that lists the paid
orders and the orders that are still open.

**UC2.2 No exact match.**
The bot registers nothing. It reports the closest total it found and returns to the previous menu. The closest total is
the achievable total nearest to the amount entered, lower or higher. The lower total wins a tie. The admin can enter
another amount.

**UC2.3 More than one exact match.**
The bot chooses the set that contains the oldest orders. The admin sees the selected orders before confirming.

**UC2.4 Pay everything.**
The admin can still mark all open orders of a customer as paid. This stays a separate choice.

**UC2.5 Open amounts for the customer.**
`/send_payment_reminder` and `/payment_info` already list only the open orders, with their amounts. After a partial
payment, they show only what is left to pay. They do not change.

**UC2.6 Overview of open payments for the admin.**
The new command `/list_open_payments` lists the customers that have open orders. It shows the open total, the number
of open orders, and the age of the oldest open order. The list is paginated and sorted with the oldest open order
first. It is also a button in the admin panel. From the list, the admin can go to the payment flow of a customer.

**UC2.7 Reports.**
Reports work as before. Each paid order is one payment event, dated when the bot marked it as paid. An order with an
amount due of zero is still an order: its event of 0.00 counts in the number of orders. A customer who
pays in several steps appears in `/report_customer`, `/report_sales_by_period` and `/report_top_customers` with each
step.

### Rules

- Only the admin can register a payment.
- The bot never selects an order that is not open.
- The bot never selects an order with an amount due of zero when it looks for a set that adds up to the amount.
  Instead, every confirmed payment also marks all zero-due open orders of the customer as paid. The confirmation list
  shows them with an amount of 0.00. This keeps a free order from staying open.
- A guest can be paid in the same way. The bot sends no message to a guest, as today.
- An order that is already paid is never part of a later selection.

### Edge cases for the design

- The amount is zero, negative, not a number, or has more than two decimals: the bot shows an error.
- A customer has many open orders: the search for an exact set must stay fast and have a limit. At the limit, the bot
  tells the admin. It must not give a wrong answer.
- An order changes between the proposal and the confirmation, for example it is cancelled or paid: the bot refuses the
  confirmation. The admin starts again.

---

## Next step

Build the changes in the order given in the two technical designs.
