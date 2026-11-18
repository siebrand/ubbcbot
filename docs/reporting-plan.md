# Order-history reporting

Status: **implemented** (2026-11-18): `services/reporting.py` (periods, buckets, totals) and
`handlers/admin/report_commands.py` (the commands). The decisions taken during the implementation are marked
**Implemented:** below; the README section "Purchase Reports" describes the result.

The order-history table is a purchase-analytics event store. Each row is one of
two events, with no personal data (only a pseudonymous `customer_id`):

| Attribute     | Meaning                                                                 |
|---------------|-------------------------------------------------------------------------|
| `history_id`  | PK (uuid)                                                               |
| `customer_id` | pseudonymous customer reference                                         |
| `offer_name`  | product name (denormalized, not PII)                                    |
| `event_type`  | `ORDER_CREATED` or `PAYMENT_RECEIVED`                                   |
| `changed_at`  | ISO-8601 timestamp                                                      |
| `amount`      | euro value (ordered value for CREATED, paid value for PAYMENT_RECEIVED) |
| `ttl`         | expiry (8 years prod / 90 days test)                                    |

Query access is via the GSI `event-time-index`
(hash `event_type`, range `changed_at`), exposed as
`OrderHistoryRepository.get_events_by_type(event_type, start_date, end_date)`.

**Implemented:** the table also has the `customer-index` (hash `customer_id`, range `changed_at`), added for the
personal data export. `get_events_by_customer(customer_id, start_date, end_date)` takes a date range now, so
`/report_customer` reads only that customer's events instead of all payments. Both queries follow
`LastEvaluatedKey` (they read only the first 1 MB before). No new index was needed.

Customer names are **not** stored here; reporting resolves the current name at
report time via `db.get_customer(customer_id)`. Names are shown in the **same
public format as the group/channel notification** — "Firstname L" (first name +
first letter of last name, falling back to username, then "unknown"), i.e. the
existing `_get_public_name` logic (`order_commands.py`). Do not show full last
names in reports. After a customer is anonymized (right-to-be-forgotten),
reports show the id / "deleted" — which is correct.

## Period / date-range parameter

Both reports take an optional period argument, parsed as follows. All dates use
the **ISO-8601** notation (`YYYY-MM-DD`); a year is `YYYY`.

- **No argument** → the current year, from 1 January until now (**implemented**).
- **A single year `YYYY`** → the full calendar year, `YYYY-01-01` through
  `YYYY-12-31` (inclusive).
- **A single date `YYYY-MM-DD`** → from that date through now (inclusive).
- **Two dates `YYYY-MM-DD YYYY-MM-DD`** → the inclusive range between them,
  ordered low→high regardless of the order given.

"Inclusive" means the end day is fully covered: the upper bound is the end of
that day (`23:59:59.999…`), so `changed_at` comparisons must use the end of the
day, not midnight.

**Implemented:** days are days in Dutch time (Europe/Amsterdam); the bounds are converted to UTC, the zone
`changed_at` is stored in. A period never runs past now (the current year stops today), and a start date in the
future is refused. Anything else (three words, `2026-02-30`, a year mixed with a date) shows the usage.

## Admin commands

### `/report_top_customers [period]`

Answers "who are the top customers per time period", ranked by **euro spend**.

Implementation sketch:

- `events = get_events_by_type("PAYMENT_RECEIVED", start, end)` for the period.
- Aggregate `sum(amount)` per `customer_id`.
- Sort descending, take top N (**implemented:** N = 10; ties by number of payments).
- Resolve each `customer_id` to a display name via `db.get_customer(...)` and
  the shared public-name format ("Firstname L", as in the channel notification /
  `_get_public_name`); fall back to the id / "verwijderd" if the customer no
  longer exists. **Implemented:** `✗ <first 8 characters of the id>`, with a one-line legend under the table
  (the word "verwijderd" did not fit the name column next to the id).

### `/report_sales_by_period [period] [granularity]`

Answers "when do customers buy the most".

Implementation sketch:

- `events = get_events_by_type("ORDER_CREATED", start, end)` for the window (use `PAYMENT_RECEIVED` instead for realized
  revenue over time).
- Bucket `changed_at` by the chosen granularity (day / week / month).
- Report order count and `sum(amount)` per bucket.

**Implemented:** granularity `day|week|month` (also `dag|maand`), default `month`; the word `paid` (`betaald`)
switches to `PAYMENT_RECEIVED`. Words may come in any order. Weeks are ISO weeks (`2026-W47`). Every bucket of the
period is listed (a dash when empty) unless there would be more than 62; then only buckets with sales. Each row has
a bar relative to the best bucket, and the footer gives the total and the best bucket.

### `/report_customer <customer> [period]`

Answers "what did this specific customer pay, and what do they still owe".

Two parts for one customer:

1. **Paid per month** over the period: `PAYMENT_RECEIVED` events for this
   `customer_id`, bucketed by **month**, summing `amount`. **Implemented:** read through the
   `customer-index` with the period as key condition, and filtered to `PAYMENT_RECEIVED` in code.
2. **Open order amount** — a single number: the sum of `total_price` of this
   customer's **non-paid** orders, read from the **live orders table**
   (`db.get_orders_by_customer(customer_id)`), *not* from the history table.
   The history table only records ORDER_CREATED / PAYMENT_RECEIVED events and
   cannot represent the current outstanding balance (e.g. a later cancellation).

Non-paid = every order status **except** `completed` (paid) and `cancelled`.
This matches the existing "outstanding total" logic in
`base_order_handler.py` (which excludes exactly `cancelled` and `completed`).
In practice the live non-paid statuses are `pending`, `ordered`,
`received_partial_delayed`, `ready_for_labeling`, `labeling_completed` and
`awaiting_payment` — "from open through awaiting payment". (The `delivered`
order status is defined in the enum but is **not used**: no code path sets an
order to it — delivery is tracked on boxes, not orders — so it can be ignored
here.)

Display the customer with the same public-name format as above.

**Implemented:** `<customer>` is a name, username or (partial) customer ID; up to two period words at the end are
the period. When several customers match, buttons ask which one; each carries the period
(`rptc_<YYYYMMDD-YYYYMMDD>_<customer_id>`, at most 59 bytes), so the choice shows the same report. The open amount is
the current state, whatever the period.

## Notes

- All reports are read-only and admin-only.
- Neither stores nor logs personal data; names are only resolved for display.
- `amount` is present on both event types, so an "ordered value vs realized
  revenue" comparison is possible later without a schema change.
- The commands are in `COMMAND_ROUTES` (admin only), `/help reports`, the admin command menu
  (`telegram-commands.json`; run `setup-commands.sh` to publish it) and a Reports section of `/admin` with buttons
  for the current year (top customers, orders per month and per week, payments per month, and a customer report
  that asks for the customer).
- A failed database read shows an error, never an empty report.
