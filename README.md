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

*Note: The deployment script automatically sets the Telegram webhook and configures bot commands with proper scopes (
admin commands only visible to chat administrators).*

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

These commands are set up in the deployment script, throught bash script setup-commands.sh.

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
- `/update_user <username|customer_id> <new_first_name> [new_last_name]` - Update customer name (customer_id may be a partial UUID of 8+ characters, like order IDs)
- `/update_user_first_name <customer_id> <new_first_name>` - Update customer first name
- `/update_user_last_name <customer_id> <new_last_name>` - Update customer last name
- `/delete_user <username|customer_id>` - Delete a customer record (right to be forgotten). Refused while the customer has orders that are not completed or cancelled (not yet delivered and/or unpaid) or a non-zero credit balance. Orders, credit transactions and purchase history are kept
- `/export_user_data <username|customer_id>` - Build the personal data export (zip with JSON, see "Personal Data Export") of a customer for an access request. Sent to the admin's private chat, not limited to once a month, and removed after an hour
- `/clear_data_export <username|customer_id>` - Clear a customer's last data export time so they can use `/my_data` again before the 30 days are over (the customer's own data and past exports are untouched)
- `/process_delivery` - Process wholesale deliveries and manage delivery status
- `/process_labeling` - Complete labeling process for delivered orders
- `/send_delivery_overviews` - Send delivery overviews to customers
- `/process_payment` - Mark customers as paid
- `/send_payment_reminder` - Send payment reminder to customers awaiting payment
- `/failed_notifications` - View orders with failed delivery notifications
- `/offer_status <offer_id> import` - Change offer status to import (for import workflow)
- `/import_orders` - Import orders from CSV file
- `/finalize_import <offer_id>` - Finalize imported offer
- `/delete_old_orders` - Delete cancelled and completed orders older than 7 days
- `/delete_cancelled_orders` - Delete all cancelled orders from database
- `/delete_completed_orders` - Delete all completed orders from database
- `/audit_orders` - Audit orders - add update_date to orders missing it
- `/cancel` - Cancel pending operation (e.g., text input prompts)

### Customer Commands

- `/start` - Register and view help
- `/help [section]` - Show help for specific section (general, orders)
- `/cancel` - Cancel pending operation (e.g., text input prompts)
- `/fomo` - View active offers you haven't ordered yet
- `/create_order <offer_id> [quantity]` - Place order (alias: /order)
- `/confirm_order <offer_id> <quantity>` - Confirm duplicate order
- `/list_my_orders [id]` - View personal orders (alias: /my_orders)
- `/list_offers` - View available offers
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
pip install -r tests/requirements.txt
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
  index is the only table change; DynamoDB builds it for the existing rows on the first deploy.
- **Not included**: data Telegram keeps itself, technical logs (7 days) and short-lived message tracking records.

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

- Wholesale box sizes: 1,2,6,8,10,12,15,16,18,20,24 units
- Auto-create new boxes when capacity reached
- Box status: open → full → ordered → delivered
- Admin access controlled via ADMIN_USER_ID environment variable

## Environment Management

- **Test**: All messages prefixed with "TEST - "
- **Production**: Clean messages
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