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
curl -s -X POST --max-time 20 "https://api.telegram.org/bot$TELEGRAM_TOKEN/setMyCommands" \
     -H "Content-Type: application/json" \
     -d "{
       \"commands\": [
         {\"command\": \"start\", \"description\": \"Register and view help\"},
         {\"command\": \"help\", \"description\": \"Show help for specific section\"},
         {\"command\": \"order\", \"description\": \"Place order: /order <offer_id> [quantity]\"},
         {\"command\": \"my_orders\", \"description\": \"View your orders\"},
         {\"command\": \"confirm_order\", \"description\": \"Confirm duplicate order\"},
         {\"command\": \"list_offers\", \"description\": \"View available offers\"},
         {\"command\": \"setup_test_data\", \"description\": \"Setup test data (test env only)\"},
         {\"command\": \"add_supplier\", \"description\": \"Add supplier\"},
         {\"command\": \"retire_supplier\", \"description\": \"Retire supplier\"},
         {\"command\": \"list_suppliers\", \"description\": \"View all suppliers\"},
         {\"command\": \"edit_supplier\", \"description\": \"Edit supplier details\"},
         {\"command\": \"update_supplier_name\", \"description\": \"Update supplier name\"},
         {\"command\": \"update_supplier_contact\", \"description\": \"Update supplier contact\"},
         {\"command\": \"create_offer\", \"description\": \"Create draft offer\"},
         {\"command\": \"offer_details\", \"description\": \"View and edit offer details\"},
         {\"command\": \"update_offer_name\", \"description\": \"Update offer name\"},
         {\"command\": \"update_offer_price\", \"description\": \"Update offer price\"},
         {\"command\": \"update_offer_description\", \"description\": \"Update offer description\"},
         {\"command\": \"publish_offer\", \"description\": \"Publish draft offer\"},
         {\"command\": \"preview_offer\", \"description\": \"Preview offer appearance\"},
         {\"command\": \"cancel_offer\", \"description\": \"Cancel offer and all orders\"},
         {\"command\": \"add_box\", \"description\": \"Add box to offer\"},
         {\"command\": \"box_status\", \"description\": \"View box status\"},
         {\"command\": \"order_wholesale\", \"description\": \"Start wholesale ordering\"},
         {\"command\": \"order_for\", \"description\": \"Place order for user\"},
         {\"command\": \"cancel_order\", \"description\": \"Cancel order\"},
         {\"command\": \"user_orders\", \"description\": \"View user orders\"},
         {\"command\": \"all_orders\", \"description\": \"Download orders CSV\"},
         {\"command\": \"pending_users\", \"description\": \"View users awaiting approval\"},
         {\"command\": \"list_users\", \"description\": \"View all customers\"},
         {\"command\": \"list_subscribers\", \"description\": \"View subscribers\"},
         {\"command\": \"approve_user\", \"description\": \"Approve user\"},
         {\"command\": \"reject_user\", \"description\": \"Reject user\"},
         {\"command\": \"user_status\", \"description\": \"Check user status\"},
         {\"command\": \"update_user\", \"description\": \"Update user name\"},
         {\"command\": \"update_user_first_name\", \"description\": \"Update user first name\"},
         {\"command\": \"update_user_last_name\", \"description\": \"Update user last name\"},
         {\"command\": \"create_discount\", \"description\": \"Create discount\"},
         {\"command\": \"cancel_discount\", \"description\": \"Cancel discount\"},
         {\"command\": \"discount_status\", \"description\": \"View discount status\"},
         {\"command\": \"wholesale_delivery\", \"description\": \"Process wholesale deliveries\"},
         {\"command\": \"labeling_completed\", \"description\": \"Complete labeling process\"},
         {\"command\": \"send_overviews\", \"description\": \"Send delivery overviews\"},
         {\"command\": \"mark_paid\", \"description\": \"Mark customers as paid\"},
         {\"command\": \"failed_notifications\", \"description\": \"View failed delivery notifications\"},
         {\"command\": \"delete_old_cancelled\", \"description\": \"Delete old cancelled orders (7+ days)\"},
         {\"command\": \"audit_orders\", \"description\": \"Audit orders - add update_date to orders missing it\"},
         {\"command\": \"admin\", \"description\": \"Admin panel with buttons\"},
         {\"command\": \"cancel\", \"description\": \"Cancel pending operation\"}
       ],
       \"scope\": {\"type\": \"chat_administrators\", \"chat_id\": \"$DEFAULT_GROUP_ID\"}
     }" | jq .

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
         {"command": "delete_cancelled", "description": "Delete all cancelled orders"},
         {"command": "list_offers", "description": "View available offers"},
         {"command": "offer_details", "description": "View offer details"},
         {"command": "subscribe", "description": "Subscribe to offer notifications"},
         {"command": "unsubscribe", "description": "Unsubscribe from offer notifications"},
         {"command": "changelog", "description": "View bot updates and changes"},
         {"command": "cancel", "description": "Cancel pending operation"}
       ],
       "scope": {"type": "default"}
     }' | jq .

echo ""
echo "✅ Bot commands configured successfully!"