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
echo "👑 Setting admin commands (private chat)..."
curl -s -X POST --max-time 20 "https://api.telegram.org/bot$TELEGRAM_TOKEN/setMyCommands" \
     -H "Content-Type: application/json" \
     -d '{
       "commands": [
         {"command": "start", "description": "Register and view help"},
         {"command": "help", "description": "Show help for specific section"},
         {"command": "admin", "description": "Admin panel with buttons"},
         {"command": "order", "description": "Place order: /order <offer_id> [quantity]"},
         {"command": "my_orders", "description": "View your orders"},
         {"command": "list_offers", "description": "View available offers"},
         {"command": "view_offer", "description": "View offer details"},
         {"command": "setup_test_data", "description": "Setup test data (test env only)"},
         {"command": "create_supplier", "description": "Create supplier"},
         {"command": "list_suppliers", "description": "View all suppliers"},
         {"command": "create_offer", "description": "Create draft offer"},
         {"command": "publish_offer", "description": "Publish draft offer"},
         {"command": "list_boxes", "description": "View box status"},
         {"command": "process_wholesale", "description": "Start wholesale ordering"},
         {"command": "order_for", "description": "Place order for user"},
         {"command": "cancel_order", "description": "Cancel order"},
         {"command": "export_orders", "description": "Download orders CSV"},
         {"command": "list_pending", "description": "View users awaiting approval"},
         {"command": "list_users", "description": "View all customers"},
         {"command": "create_guest", "description": "Add guest user"},
         {"command": "list_guests", "description": "View guest users"},
         {"command": "process_delivery", "description": "Process wholesale deliveries"},
         {"command": "process_labeling", "description": "Complete labeling process"},
         {"command": "send_delivery_overviews", "description": "Send delivery overviews"},
         {"command": "process_payment", "description": "Mark customers as paid"},
         {"command": "create_discount", "description": "Create discount"},
         {"command": "view_discount", "description": "View discount status"},
         {"command": "cancel", "description": "Cancel pending operation"}
       ],
       "scope": {"type": "chat_member", "chat_id": 15005473, "user_id": 15005473}
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
         {"command": "cancel", "description": "Cancel pending operation"}
       ],
       "scope": {"type": "default"}
     }' | jq .

echo ""
echo "✅ Bot commands configured successfully!"