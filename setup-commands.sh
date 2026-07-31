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

echo "🗑️  Removing group commands..."
curl -s -X POST --max-time 20 "https://api.telegram.org/bot$TELEGRAM_TOKEN/deleteMyCommands" \
     -H "Content-Type: application/json" \
     -d "{
       \"scope\": {\"type\": \"chat_administrators\", \"chat_id\": \"$DEFAULT_GROUP_ID\"}
     }" | jq .

echo ""
echo "🗑️  Removing group member commands..."
curl -s -X POST --max-time 20 "https://api.telegram.org/bot$TELEGRAM_TOKEN/deleteMyCommands" \
     -H "Content-Type: application/json" \
     -d "{
       \"scope\": {\"type\": \"chat\", \"chat_id\": \"$DEFAULT_GROUP_ID\"}
     }" | jq .

echo ""
echo "🗑️  Removing all group chats commands..."
curl -s -X POST --max-time 20 "https://api.telegram.org/bot$TELEGRAM_TOKEN/deleteMyCommands" \
     -H "Content-Type: application/json" \
     -d '{
       "scope": {"type": "all_group_chats"}
     }' | jq .

echo ""
echo "👥 Setting customer commands..."
curl -s -X POST --max-time 20 "https://api.telegram.org/bot$TELEGRAM_TOKEN/setMyCommands" \
     -H "Content-Type: application/json" \
     -d '{
       "commands": [
         {"command": "start", "description": "Register and view help"},
         {"command": "help", "description": "Show help for specific section"},
         {"command": "order", "description": "Place order: /order <offer_id> [quantity]"},
         {"command": "my_orders", "description": "View your orders"},
         {"command": "confirm_order", "description": "Confirm duplicate order"},
         {"command": "payment_info", "description": "View payment details"},
         {"command": "delete_cancelled_orders", "description": "Delete all cancelled orders"},
         {"command": "delete_completed_orders", "description": "Delete all completed orders"},
         {"command": "list_offers", "description": "View available offers"},
         {"command": "view_offer", "description": "View offer details"},
         {"command": "subscribe", "description": "Subscribe to offer notifications"},
         {"command": "unsubscribe", "description": "Unsubscribe from offer notifications"},
         {"command": "changelog", "description": "View bot updates and changes"},
         {"command": "fomo", "description": "View active offers you haven't ordered yet"},
         {"command": "cancel", "description": "Cancel pending operation"}
       ],
       "scope": {"type": "default"}
     }' | jq .

echo ""
echo "✅ Bot commands configured successfully!"