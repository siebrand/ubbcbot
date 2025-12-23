#!/bin/bash

# UBBC Bot Commands Setup Script
set -e

ENVIRONMENT=${1:-test}

if [ "$ENVIRONMENT" != "test" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "Usage: $0 <environment>"
    echo "Environment: test or prod"
    exit 1
fi

echo "🤖 Setting up bot commands for $ENVIRONMENT environment..."

# Get bot token
TELEGRAM_TOKEN=$(aws ssm get-parameter \
    --name "/ubbc-bot/$ENVIRONMENT/telegram-bot-token" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text)

# Get default group ID for command scope
if [ "$ENVIRONMENT" = "test" ]; then
    DEFAULT_GROUP_ID="-1003399818858"
else
    DEFAULT_GROUP_ID="-1001662432692"
fi

echo "👑 Setting admin commands..."
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/setMyCommands" \
     -H "Content-Type: application/json" \
     -d "{
       \"commands\": [
         {\"command\": \"start\", \"description\": \"Register and view help\"},
         {\"command\": \"order\", \"description\": \"Place order: /order <offer_id> [quantity]\"},
         {\"command\": \"my_orders\", \"description\": \"View your orders\"},
         {\"command\": \"confirm_order\", \"description\": \"Confirm duplicate order\"},
         {\"command\": \"list_offers\", \"description\": \"View available offers\"},
         {\"command\": \"setup_test_data\", \"description\": \"Setup test data (test env only)\"},
         {\"command\": \"add_supplier\", \"description\": \"Add supplier\"},
         {\"command\": \"create_offer\", \"description\": \"Create offer\"},
         {\"command\": \"list_suppliers\", \"description\": \"View all suppliers\"},
         {\"command\": \"box_status\", \"description\": \"View box status\"},
         {\"command\": \"fulfill_offer\", \"description\": \"Start offer fulfillment\"},
         {\"command\": \"confirm_fulfill\", \"description\": \"Confirm fulfillment\"},
         {\"command\": \"order_for\", \"description\": \"Place order for user\"},
         {\"command\": \"cancel_order\", \"description\": \"Cancel order\"},
         {\"command\": \"confirm_cancel\", \"description\": \"Confirm order cancellation\"},
         {\"command\": \"user_orders\", \"description\": \"View user orders\"},
         {\"command\": \"all_orders\", \"description\": \"Download orders CSV\"},
         {\"command\": \"pending_users\", \"description\": \"View users awaiting approval\"},
         {\"command\": \"approve_user\", \"description\": \"Approve user\"},
         {\"command\": \"reject_user\", \"description\": \"Reject user\"},
         {\"command\": \"user_status\", \"description\": \"Check user status\"},
         {\"command\": \"update_customer\", \"description\": \"Update customer name\"}
       ],
       \"scope\": {\"type\": \"chat_administrators\", \"chat_id\": \"$DEFAULT_GROUP_ID\"}
     }" | jq .

echo ""
echo "👥 Setting customer commands..."
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/setMyCommands" \
     -H "Content-Type: application/json" \
     -d '{
       "commands": [
         {"command": "start", "description": "Register and view help"},
         {"command": "order", "description": "Place order: /order <offer_id> [quantity]"},
         {"command": "my_orders", "description": "View your orders"},
         {"command": "confirm_order", "description": "Confirm duplicate order"},
         {"command": "list_offers", "description": "View available offers"},
         {"command": "subscribe", "description": "Subscribe to offer notifications"},
         {"command": "unsubscribe", "description": "Unsubscribe from offer notifications"}
       ],
       "scope": {"type": "default"}
     }' | jq .

echo ""
echo "✅ Bot commands configured successfully!"