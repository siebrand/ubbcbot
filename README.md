# UBBC Bot - Stage 1 Core Infrastructure

Telegram beer ordering bot with AWS serverless architecture.

## Quick Start

### Prerequisites

- ✅ AWS CLI configured
- ✅ AWS SAM CLI installed
- ✅ Telegram bot token from @BotFather

## Telegram Bot Setup

### ✅ Test Environment Setup

1. **Create test bot with @BotFather:**
    - Send `/newbot` to @BotFather
    - Choose name ending with "Test" (e.g., "UBBC Test Bot")
    - Choose username ending with "test_bot" (e.g., "ubbc_test_bot")
    - Save the bot token for Parameter Store

2. **Configure test bot:**
    - Send `/setdescription` to @BotFather
    - Select your test bot
    - Set: "TEST - Beer ordering bot for UBBC (Test Environment)"

3. **Set bot description:**
    - Send `/setdescription` to @BotFather
    - Select your test bot
    - Set: "TEST - Beer ordering bot for UBBC (Test Environment)"

4. **Add bot to test group:**
    - Create or use existing test group (e.g., "UBBC Test Group")
    - Add the test bot to the group
    - Make the bot an admin with permissions:
        - Delete messages
        - Restrict members
        - Pin messages
        - Manage video chats

### ✅Production Environment Setup

1. **Create production bot with @BotFather:**
    - Send `/newbot` to @BotFather
    - Choose production name (e.g., "UBBC Bot")
    - Choose production username (e.g., "ubbc_bot")
    - Save the bot token for Parameter Store

2. **Configure production bot:**
    - Send `/setdescription` to @BotFather
    - Select your production bot
    - Set: "Beer ordering bot for UBBC - Order craft beers"

3. **Set bot description:**
    - Send `/setdescription` to @BotFather
    - Select your production bot
    - Set: "Beer ordering bot for UBBC - Order craft beers"

4. **Add bot to production groups:**
    - Add the bot to UBBC main group/channel
    - Make the bot an admin with permissions:
        - Delete messages
        - Restrict members
        - Pin messages
        - Manage video chats
    - Consider adding to additional relevant groups (regional, special events)

## Deployment

1. ✅**Configure admin user ID:**

Edit `samconfig.toml` and replace `<YOUR_TELEGRAM_USER_ID>` with your Telegram user ID:

```toml
[test.deploy.parameters]
parameter_overrides = "Environment=test AdminUserId=YOUR_TELEGRAM_USER_ID"

[prod.deploy.parameters]
parameter_overrides = "Environment=prod AdminUserId=YOUR_TELEGRAM_USER_ID"
```

To find your Telegram user ID, send a message to @userinfobot on Telegram.

2. ✅**Store bot tokens in Parameter Store:**
2. ✅**Store bot tokens in Parameter Store:**

```bash
# For test environment (use token from test bot creation)
aws ssm put-parameter \
    --name "/ubbc-bot/test/telegram-bot-token" \
    --value "YOUR_TEST_BOT_TOKEN" \
    --type "SecureString"

# For production environment (use token from production bot creation)
aws ssm put-parameter \
    --name "/ubbc-bot/prod/telegram-bot-token" \
    --value "YOUR_PROD_BOT_TOKEN" \
    --type "SecureString"
```

The webhook secret (`/ubbc-bot/{environment}/telegram-webhook-secret`) is generated automatically by `deploy.sh` on
first deploy and passed to Telegram as `secret_token`. The webhook Lambda rejects (403) every request without a matching
`X-Telegram-Bot-Api-Secret-Token` header. To rotate it, delete the parameter and redeploy.

3. ✅**Deploy to test environment:**

```bash
./deploy.sh test
```

4. **Deploy to production:**

```bash
./deploy.sh prod
```

*Note: The deployment script automatically sets the Telegram webhook and configures the bot's command menus (see "Bot
Commands").*

## Post-Deployment Verification

### Test Environment Verification

1. **Test bot functionality:**
    - Send `/start` to verify registration (both private and group)
    - Admin: Use `/setup_test_data` to create test data
    - Verify all messages are prefixed with "TEST - "
    - Test group functionality: orders, announcements

### Production Environment Verification

1. **Production verification:**
    - Send `/start` to verify registration (both private and group)
    - Admin: Add real suppliers
    - Verify messages have NO "TEST - " prefix
    - Test complete order flow in production groups
    - Verify admin permissions work correctly

### ✅Webhook Verification

After deployment, verify webhook is active:

```bash
# Check webhook status
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo"
```

Expected response should show:

- `"url"`: Your API Gateway endpoint
- `"has_custom_certificate"`: false
- `"pending_update_count"`: 0

## Bot Commands

The commands Telegram suggests (the menu behind the `/` button) are set up by `setup-commands.sh`, which `deploy.sh`
runs. There are three menus, so Telegram only suggests what works where:

| Menu | Shown in | Contains |
|------|----------|----------|
| `group` | group chats | only what works in a group (`/fomo`) |
| `customer` | private chats (and the default) | the customer commands |
| `admin` | the private chat of the admin only | the customer commands and every admin command |

The menus and their descriptions are in `telegram-commands.json`. After changing it, run `./setup-commands.sh test` (or
`prod`); `DRY_RUN=1 ./setup-commands.sh test` prints the Telegram calls without making them. Tests check that the menus
only suggest commands the bot has, that customers and groups are never offered admin commands, and that the admin menu
has every admin command.

### Admin Commands

- `/admin` - Admin panel with buttons for all admin functions
- `/help [section]` - Show help for specific section (general, orders, suppliers, offers, users, delivery, import,
  system)
- `/setup_test_data` - Setup test data (test environment only)
- `/create_supplier <name>` - Register new supplier
- `/archive_supplier <name>` - Archive supplier (no longer available for new offers)
- `/list_suppliers [active|retired|all]` - View suppliers by status (default: active, paginated)
- `/update_supplier <name>` - Edit supplier details with inline keyboard
- `/update_supplier_name <supplier_id> <new_name>` - Update supplier name
- `/update_supplier_contact <supplier_id> <email>` - Update supplier contact email
- `/update_supplier_full_name <supplier_id> <new_name>` - Update supplier full name
- `/create_offer <supplier_name> <name> <price> <box_size>` - Create draft beer offer
- `/instant_order <supplier> <name> <price> <customer> [box_size]` - Create an offer, a delivered box and the first
  order at once (box size 1 to 6, default 1; quote a supplier, name or customer with spaces, see "Instant Orders")
- `/view_offer <offer_id>` - View and edit offer details
- `/update_offer_name <offer_id> <new_name>` - Update offer name
- `/update_offer_price <offer_id> <new_price>` - Update offer price
- `/update_offer_description <offer_id> <description>` - Update offer description
- `/publish_offer <offer_id>` - Publish draft offer and announce to customers
- `/cancel_offer <offer_id>` - Cancel offer and all related orders (button confirmation)
- `/delete_offer <offer_id>` - Delete completed or inactive offer from database
- `/create_box <offer_id>` - Add single box to offer (updates sold out offers to active)
- `/list_boxes [<offer_id>|active|ordered|full|delivered|all|help]` - View box status and capacity (paginated with
  enhanced navigation)
- `/audit_offer <offer_id>` - Audit offer capacity vs orders
- `/refill_boxes <offer_id>` - After cancellations, move pending orders from later boxes into the room of earlier
  ones (boxes not yet ordered) and remove the boxes that end up empty; shows the moves first (button confirmation)
- `/process_wholesale <offer_id>` - Start wholesale ordering process (button confirmation)
- `/create_order_for <username> <offer_id> [quantity]` - Place order for another user (10-unit admin limit, alias:
  /order_for)
- `/cancel_order <order_id>` - Cancel customer order (button confirmation)
- `/list_user_orders <username>` - View orders for specific user
- `/list_offer_orders <offer_id>` - View all orders for specific offer
- `/export_orders [active|cancelled|ordered|ready_for_labeling|labeling_completed|awaiting_payment|completed|all|full]` - Download CSV of all orders (default: active, full exports all fields). The file is always sent to the admin's private chat, also when requested in a group, and is deleted from the chat one hour after it was sent (see "Export expiry" below)
- `/list_pending` - View users awaiting approval (paginated with approve/reject buttons)
- `/list_users` - View all customers (paginated with status filtering)
- `/create_guest <first_name> [last_name] [contact]` - Add guest user (non-Telegram)
- `/list_guests` - View all guest users (paginated)
- `/approve_user <name_or_username>` - Approve user
- `/reject_user <name_or_username>` - Reject user
- `/user_status <name_or_username>` - Check user status
- `/update_user <username|customer_id> <new_first_name> [new_last_name]` - Update customer name (customer_id may be a partial UUID of 8+ characters, like order IDs). The edit screen also changes the status (approved, pending, rejected), so a rejected customer can be approved again. Approval is not taken away while the customer has orders that are not paid or cancelled (also not with `/reject_user`): without approval those orders would get no delivery overview, payment or reminder
- `/update_user_first_name <customer_id> <new_first_name>` - Update customer first name
- `/update_user_last_name <customer_id> <new_last_name>` - Update customer last name
- `/delete_user <username|customer_id>` - Delete a customer record (right to be forgotten). Refused while the customer has orders that are not completed or cancelled (not yet delivered and/or unpaid) or a non-zero credit balance. Orders, credit transactions and purchase history are kept
- `/export_user_data <username|customer_id>` - Build the personal data export (zip with JSON, see "Personal Data Export") of a customer for an access request. Sent to the admin's private chat, not limited to once a month, and removed after an hour
- `/clear_data_export <username|customer_id>` - Clear a customer's last data export time so they can use `/my_data` again before the 30 days are over (the customer's own data and past exports are untouched)
- `/process_delivery` - Process wholesale deliveries and manage delivery status
- `/process_labeling` - Complete labeling process for delivered orders
- `/send_delivery_overviews` - Send delivery overviews to customers
- `/process_payment` - Mark customers as paid: ✓ pays all their open orders, 💶 asks for the amount received and pays
  the oldest open orders that add up to it exactly (see "Partial Payments")
- `/list_open_payments` - Customers with unpaid orders: open total, number of orders and age of the oldest, oldest first
- `/send_payment_reminder` - Send payment reminder to customers awaiting payment
- `/failed_notifications` - Labeled orders without a delivery overview yet (an overview that could not be delivered
  is reported when it is sent)
- `/offer_status <offer_id> import` - Change offer status to import (for import workflow)
- `/import_orders` - Import orders from CSV file. If a name on any line matches more than one customer, the whole file is refused and the colliding lines are listed (use the full username or the customer ID, 8+ characters)
- `/finalize_import <offer_id>` - Finalize imported offer
- `/delete_old_orders` - Delete cancelled and completed orders older than 7 days
- `/delete_cancelled_orders` - Delete all cancelled orders from database
- `/delete_completed_orders` - Delete all completed orders from database
- `/audit_orders` - Audit orders - add update_date to orders missing it
- `/report_top_customers [period] [anon]` - Top 10 customers by amount paid in the period; with `anon` made-up names instead of the real ones (see "Purchase Reports")
- `/report_sales_by_period [period] [day|week|month] [paid]` - Number and value of the orders placed per day, week or month (default: month); with `paid` the payments received instead
- `/report_customer <username|customer_id> [period]` - What one customer paid per month in the period, and the amount of their orders that are not paid yet
- `/cancel` - Cancel pending operation (e.g., text input prompts)

### Customer Commands

- `/start` - Register and view help
- `/help [section]` - Show help for specific section (general, orders)
- `/cancel` - Cancel pending operation (e.g., text input prompts)
- `/fomo` - View active offers you haven't ordered yet
- `/create_order <offer_id> [quantity]` - Place order (alias: /order)
- `/confirm_order <offer_id> <quantity>` - Confirm duplicate order
- `/list_my_orders [id]` - View personal orders (alias: /my_orders)
- `/list_offers` - View available offers; `/list_offers sold_out` lists every sold-out offer
- `/view_offer <offer_id>` - View detailed offer information
- `/payment_info` - View payment details for pending orders
- `/subscribe` - Subscribe to new offer notifications
- `/unsubscribe` - Unsubscribe from offer notifications
- `/delete_cancelled_orders` - Delete all cancelled orders from personal register
- `/delete_completed_orders` - Delete all completed orders from personal register
- `/changelog` - View bot updates and feature changes
- `/my_data` - Download all data the bot stores about you as a zip with JSON files (approved users, once per 30 days, see "Personal Data Export")

## Static Analysis

CI runs ruff, mypy, bandit and pip-audit on every pull request, and GitHub's
CodeQL default setup scans the code. To run the first four locally:

```bash
pip install -r src/requirements.txt -r tests/requirements.txt
scripts/static-analysis.sh
```

See [docs/static-analysis.md](docs/static-analysis.md) for details.

## Architecture

- **API Gateway**: Webhook endpoint
- **Lambda**: Bot logic and command processing
- **DynamoDB**: Data storage (offers, orders, customers, boxes, suppliers, notifications)
- **S3**: Image storage for offer photos
- **Parameter Store**: Secure token storage

## Features

### Personal Data Export

- **Why**: customers have the right to a copy of their data (right of access and data portability).
- **How**: an approved customer sends `/my_data` to the bot. The webhook claims the monthly slot and starts the
  `DataExporter` Lambda asynchronously. The Lambda builds a zip with `profile.json`, `orders.json`, `credit.json`,
  `purchase_history.json` and a `README.txt` (Dutch or English, following the customer's language) and sends it to the
  customer's private chat, whatever chat the command came from.
- **Once per 30 days**: the time of the last export is stored on the customer record (`last_data_export_at`). The slot is
  claimed with one conditional DynamoDB update, so two quick requests cannot both succeed. If the export fails, the claim
  is released again, so a failure does not use up the month. A refused request shows the date it is possible again.
- **Only the customer's own data**: other customers' data is not included, and the administrator behind a credit
  transaction (`created_by`) is left out. Amounts are text with two decimals, dates are UTC.
- **Expiry**: the sent file is tracked and deleted after an hour, exactly like the admin order exports (see "Export
  Expiry"). Customers should save the file first.
- **Lookup by customer**: purchase history is read through the `customer-index` on the order history table. Adding that
  index is the only table change; DynamoDB builds it for the existing rows on the first deploy. Until that backfill has
  finished the index cannot be read ("Cannot read from backfilling global secondary index"): an export then fails with
  an error message and does not count towards the monthly limit. Wait for the index to become ACTIVE before announcing
  `/my_data`.
- **Never incomplete**: every source (orders, credit balance, credit transactions, purchase history) must be read
  successfully. A failed read fails the whole export instead of leaving that part out.
- **Not included**: data Telegram keeps itself, technical logs (7 days) and short-lived message tracking records.

### Purchase Reports

- **What**: three read-only admin commands on the order history table (purchase analytics events), also as buttons for
  the current year in the Reports section of `/admin`:
  - `/report_top_customers` ranks customers by the sum of their `PAYMENT_RECEIVED` events (top 10, with the total, the
    number of customers and the share of the total paid by the top 10). With `anon` (or `anoniem`) every customer,
    deleted ones included, gets a made-up beer name from `ANON_NAMES` (`services/reporting.py`), drawn at random each
    time and never twice in one report.
  - `/report_sales_by_period` counts `ORDER_CREATED` events (or `PAYMENT_RECEIVED` with `paid`) and sums their amount
    per day, ISO week or month, with a bar per period and the best period.
  - `/report_customer` shows a customer's payments per month, and the open order amount: the sum of `total_price` of
    their orders in the orders table that are not `completed` or `cancelled`. That amount is the current state, not
    limited to the period; the history table cannot show it, because cancellations are not recorded there.
- **Excluded customers**: the orders and payments of the customers in `EXCLUDED_CUSTOMER_IDS` (`services/reporting.py`)
  are left out of `/report_top_customers` and `/report_sales_by_period`, totals included. `/report_customer` still
  shows them.
- **Period**: `YYYY` is that calendar year, `YYYY-MM-DD` runs from that date until now, `YYYY-MM-DD YYYY-MM-DD` from the
  earlier through the later date (both whole days, in any order). Without a period: this year until now. A period
  never runs past now. Days, weeks and months are in Dutch time (Europe/Amsterdam); the stored times are UTC.
- **Names**: the history table holds only the pseudonymous `customer_id`. Names are looked up when the report is shown,
  in the public format of the group notification ("Firstname L", else the username), never with the full last name. A
  customer whose record was deleted shows as `✗` with the first 8 characters of the customer ID.
- **Indexes**: the reports use the existing `event-time-index` (event type and time) and `customer-index` (customer
  and time) of the order history table, and the `customer-index` of the orders table. No table change is needed.
- **Long reports** (for example per day over a year) are split over several messages. Periods without sales are shown
  as a dash, except when there would be more than 62 rows; then only the periods with sales are listed.

### Instant Orders

- **What**: `/instant_order` sells beer the admin already has. One write creates the offer, a box that is already
  `delivered` and holds one unit, and the customer's order (`ready_for_labeling`, placed by the admin). The customer is
  told as for `/order_for`; a guest gets nothing.
- **Box size 1**: the offer is `sold_out` at once and nothing is posted in the group.
- **Box size 2 to 6**: the offer is `active` and gets one group announcement with the order buttons (no subscriber
  messages, no customer name). Later orders go straight to `ready_for_labeling` in the same box; the order that fills
  it sells the offer out and edits the announcement. The admin can add orders with `/order_for`.
- **Input**: `/instant_order DeMolen Tripel 3.50 Jan 4`, or with quotes (straight or curly):
  `/instant_order "De Molen" "Hel & Verdoemenis" 4.50 "Jan Jansen"`. Only approved customers are matched; more than
  one match shows a list to pick from.
- **Afterwards** the offer is an ordinary offer: labeling, the delivery overview and payment work as for any other.
  An offer with a delivered box that holds orders cannot be cancelled with `/cancel_offer`.

### Partial Payments

- **What**: a customer who pays part of what is open. In `/process_payment` the 💶 button next to a customer asks for
  the amount received (`40`, `40,50`, `€40.50`; at most 10 000).
- **Whole orders only**: the bot looks for the set of open orders whose amounts due (price minus credit applied) add up
  to exactly that amount. When several sets do, the one with the oldest order wins (oldest: open the longest), then
  the next oldest. Orders with nothing due are settled along. No credit is involved: an amount that matches no set is
  not booked, and the closest total is shown.
- **Confirmation**: the proposal lists the orders and what stays open. The confirm button carries no stored state; the
  bot searches again and pays only when the same orders come out, so an order that changed in between, or a second
  tap, changes nothing. Each order is set to paid only while it still awaits payment, with its `PAYMENT_RECEIVED`
  event (amount: the order's price, as for "pay everything").
- **The customer** is told from the admin account what was received and what is still to pay (guests get nothing).
- **Limits**: more than 60 open orders, or more than €100 000 open, cannot be searched; pay those with ✓ or
  `/edit_order`.

### Export Expiry

- **Why**: an order export contains customer data and should not stay in the chat history.
- **How**: every export sent by `/export_orders` is tracked in the notifications table (`kind` `export`, `offer_id` 0)
  with an expiry one hour after it was sent. When it has expired the message is deleted from the chat.
- **Event-based, no scheduler**: expired exports are cleared whenever one of these happens: a new export, an offer
  publish or announcement (including import finalization), an offer message sync, or any update from the admin. The
  sweep runs at most once a minute per warm Lambda container. An export is therefore removed at the first of those
  events after the hour has passed, not exactly at the hour.
- **Limits**: Telegram only lets a bot delete messages younger than 48 hours; an older export is dropped from tracking
  and has to be removed by hand. Files the admin already downloaded stay on the admin's devices.
- **Recommended**: set the chat auto-delete timer in the private chat with the bot (chat menu, "Auto-delete"). Only the
  user can set it, not the bot. It removes anything that the event-based sweep has not cleared yet.

### Enhanced Wholesale Delivery

- **Complete Delivery Button**: Single-click option to mark all boxes in an offer as delivered with full quantities
- **Confirmation Dialog**: Safety confirmation before processing multiple boxes
- **Streamlined Workflow**: Reduces repetitive clicking for common full delivery scenarios
- **Individual Box Control**: Maintains granular control for partial deliveries and edge cases

### Enhanced Offer Management

- **Staged Publishing**: Create draft offers, add descriptions and images, then publish when ready
- **Rich Offer Display**: Offers include detailed descriptions and multiple images
- **Admin Preview**: Preview how offers will appear before publishing
- **Image Support**: Upload and manage multiple images per offer via S3 storage
- **Draft Status**: Draft offers visible only to admins until published

### Notification Management

- **Rich Notifications**: Offer announcements include images and descriptions
- **Live status updates**: When an offer sells out, is cancelled, or becomes available again, the group announcement and
  every subscriber DM are edited in place — a 🔴 (sold out) or ⛔ (cancelled) marker is added and the order buttons are
  removed/re-added accordingly (messages are never deleted)
- **Live content updates**: Editing an offer's name, price, or description re-renders the already-sent announcements to
  match
- **Group-first, then trickle**: The group message is edited first (one call, inline); subscriber DMs follow — inline
  for small lists, batched via the NotificationSender Lambda for large ones
- **Self-expiring tracking**: Each announcement's message id is tracked for 7 days (DynamoDB TTL) so edits stop chasing
  week-old offers; rows whose Telegram message is gone are pruned

### Order Management

- **5-unit customer limit**: Customers can order max 5 units per offer
- **10-unit admin limit**: Admins can place up to 10 units for customers via `/order_for`
- **Duplicate order confirmation**: Warns customers about existing orders before placing new ones
- **Sold out notifications**: Group notifications include "SOLD OUT" status when last item ordered

## Business Rules

- Box sizes: 1 to 6, 8, 9, 10, 12, 15, 16, 18, 20 and 24 units (`/instant_order`: 1 to 6)
- Auto-create new boxes when capacity reached
- Box status: open → full → ordered → delivered
- Admin access controlled via ADMIN_USER_ID environment variable

## Environment Management

- **Test**: All messages prefixed with "TEST - "
- **Production**: Clean messages
- Admin commands and admin button taps in a group are answered in the admin's private chat in both environments, so
  text prompts (edit contexts) only ever exist in, and are only read from, the private chat
- Environment-specific configuration via Parameter Store

## Resource Naming

All resources follow: `ubbc-bot-{environment}-{resource-type}`

Examples:

- `ubbc-bot-test-webhook-handler`
- `ubbc-bot-prod-customers`
- `ubbc-bot-test-123456789-images`

## Success Criteria ✓

- [x] Deploy via AWS SAM to test and production
- [x] Accept Telegram webhooks with validation
- [x] Admin commands for supplier and offer management
- [x] Customer order processing with validation
- [x] Box status and capacity tracking
- [x] Persistent DynamoDB storage
- [x] Admin access control via environment variable
- [x] Resource naming convention and tagging
- [x] Environment-specific configuration
- [x] Order cancellation with inventory correction and customer notification
- [x] Notification message cleanup for sold out and cancelled offers
- [x] Order limits and duplicate order handling
- [x] Sold out status in group notifications