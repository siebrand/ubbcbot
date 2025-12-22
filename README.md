# UBBC Bot - Stage 1 Core Infrastructure

Telegram beer ordering bot with AWS serverless architecture.

## Quick Start

### Prerequisites
- AWS CLI configured
- AWS SAM CLI installed
- Telegram bot token from @BotFather

### Deployment

1. **Deploy to test environment:**
```bash
./deploy.sh test YOUR_TEST_BOT_TOKEN
```

2. **Deploy to production:**
```bash
./deploy.sh prod YOUR_PROD_BOT_TOKEN
```

3. **Set Telegram webhook:**
```bash
# Use the webhook URL from deployment output
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook" \
     -d "url=YOUR_WEBHOOK_URL"
```

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