# UBBC Bot - Stage 1 Core Infrastructure

Telegram beer ordering bot with AWS serverless architecture.

## Quick Start

### Prerequisites
- AWS CLI configured
- AWS SAM CLI installed
- Telegram bot token from @BotFather

## Telegram Bot Setup

### Test Environment Setup

1. **Create test bot with @BotFather:**
   - Send `/newbot` to @BotFather
   - Choose name ending with "Test" (e.g., "UBBC Test Bot")
   - Choose username ending with "test_bot" (e.g., "ubbc_test_bot")
   - Save the bot token for Parameter Store

2. **Configure test bot:**
   - Send `/setdescription` to @BotFather
   - Select your test bot
   - Set: "TEST - Beer ordering bot for UBBC (Test Environment)"

3. **Set bot commands:**
   - Send `/setcommands` to @BotFather
   - Select your test bot
   - Paste:
   ```
   start - Register and view help
   order - Place order: /order <offer_id> <quantity>
   my_orders - View your orders
   add_supplier - [Admin] Add supplier: /add_supplier <name>
   create_offer - [Admin] Create offer: /create_offer <supplier_id> <name> <price> <box_size>
   list_offers - [Admin] View all offers
   box_status - [Admin] View box status
   ```

4. **Add bot to test group:**
   - Create or use existing test group (e.g., "UBBC Test Group")
   - Add the test bot to the group
   - Make the bot an admin with permissions:
     - Delete messages
     - Restrict members
     - Pin messages
     - Manage video chats

### Production Environment Setup

1. **Create production bot with @BotFather:**
   - Send `/newbot` to @BotFather
   - Choose production name (e.g., "UBBC Bot")
   - Choose production username (e.g., "ubbc_bot")
   - Save the bot token for Parameter Store

2. **Configure production bot:**
   - Send `/setdescription` to @BotFather
   - Select your production bot
   - Set: "Beer ordering bot for UBBC - Order craft beers by the box"

3. **Set bot commands:**
   - Send `/setcommands` to @BotFather
   - Select your production bot
   - Paste the same commands as test environment

4. **Add bot to production groups:**
   - Add the bot to UBBC main group/channel
   - Make the bot an admin with permissions:
     - Delete messages
     - Restrict members
     - Pin messages
     - Manage video chats
   - Consider adding to additional relevant groups (regional, special events)

## Deployment

1. **Store bot tokens in Parameter Store:**
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

2. **Deploy to test environment:**
```bash
./deploy.sh test
```

3. **Deploy to production:**
```bash
./deploy.sh prod
```

*Note: The deployment script automatically sets the Telegram webhook using the bot token from Parameter Store.*

## Post-Deployment Verification

### Test Environment Verification

1. **Test bot functionality:**
   - Send `/start` to verify registration (both private and group)
   - Admin (ID: 15005473): Test `/add_supplier Test Supplier`
   - Verify all messages are prefixed with "TEST - "
   - Test group functionality: orders, announcements

### Production Environment Verification

1. **Production verification:**
   - Send `/start` to verify registration (both private and group)
   - Admin (ID: 15005473): Add real suppliers
   - Verify messages have NO "TEST - " prefix
   - Test complete order flow in production groups
   - Verify admin permissions work correctly

### Webhook Verification

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

### Admin Commands (User ID: 15005473)
- `/add_supplier <name>` - Register new supplier
- `/create_offer <supplier_id> <name> <price> <box_size>` - Create beer offer
- `/list_offers` - View all active offers
- `/box_status` - View box status and capacity

### Customer Commands
- `/start` - Register and view help
- `/order <offer_id> <quantity>` - Place order
- `/my_orders` - View personal orders

## Architecture

- **API Gateway**: Webhook endpoint
- **Lambda**: Bot logic and command processing
- **DynamoDB**: Data storage (offers, orders, customers, boxes, suppliers)
- **S3**: Image storage (ready for future use)
- **Parameter Store**: Secure token storage

## Business Rules

- Wholesale box sizes: 1,2,6,8,10,12,15,16,18,20,24 units
- Auto-create new boxes when capacity reached
- Box status: open → minimum_reached → full → ordered → delivered
- Admin restricted to user ID 15005473

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
- [x] Admin access control (ID: 15005473)
- [x] Resource naming convention and tagging
- [x] Environment-specific configuration