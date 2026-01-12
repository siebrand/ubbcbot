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
         {\"command\": \"create_supplier\", \"description\": \"Create supplier\"},
         {\"command\": \"archive_supplier\", \"description\": \"Archive supplier\"},
         {\"command\": \"list_suppliers\", \"description\": \"View all suppliers\"},
         {\"command\": \"update_supplier\", \"description\": \"Update supplier details\"},
         {\"command\": \"update_supplier_name\", \"description\": \"Update supplier name\"},
         {\"command\": \"update_supplier_contact\", \"description\": \"Update supplier contact\"},
         {\"command\": \"create_offer\", \"description\": \"Create draft offer\"},
         {\"command\": \"view_offer\", \"description\": \"View and edit offer details\"},
         {\"command\": \"update_offer_name\", \"description\": \"Update offer name\"},
         {\"command\": \"update_offer_price\", \"description\": \"Update offer price\"},
         {\"command\": \"update_offer_description\", \"description\": \"Update offer description\"},
         {\"command\": \"offer_status\", \"description\": \"Change offer status to import\"},
         {\"command\": \"import_orders\", \"description\": \"Import orders from CSV file\"},
         {\"command\": \"finalize_import\", \"description\": \"Finalize imported offer\"},
         {\"command\": \"publish_offer\", \"description\": \"Publish draft offer\"},
         {\"command\": \"preview_offer\", \"description\": \"Preview offer appearance\"},
         {\"command\": \"cancel_offer\", \"description\": \"Cancel offer and all orders\"},
         {\"command\": \"create_box\", \"description\": \"Add box to offer\"},
         {\"command\": \"list_boxes\", \"description\": \"View box status\"},
         {\"command\": \"process_wholesale\", \"description\": \"Start wholesale ordering\"},
         {\"command\": \"order_for\", \"description\": \"Place order for user\"},
         {\"command\": \"cancel_order\", \"description\": \"Cancel order\"},
         {\"command\": \"list_user_orders\", \"description\": \"View user orders\"},
         {\"command\": \"export_orders\", \"description\": \"Download orders CSV\"},
         {\"command\": \"list_pending\", \"description\": \"View users awaiting approval\"},
         {\"command\": \"list_users\", \"description\": \"View all customers\"},
         {\"command\": \"list_subscribers\", \"description\": \"View subscribers\"},
         {\"command\": \"create_guest\", \"description\": \"Add guest user (non-Telegram)\"},
         {\"command\": \"list_guests\", \"description\": \"View guest users\"},
         {\"command\": \"approve_user\", \"description\": \"Approve user\"},
         {\"command\": \"reject_user\", \"description\": \"Reject user\"},
         {\"command\": \"user_status\", \"description\": \"Check user status\"},
         {\"command\": \"update_user\", \"description\": \"Update user name\"},
         {\"command\": \"update_user_first_name\", \"description\": \"Update user first name\"},
         {\"command\": \"update_user_last_name\", \"description\": \"Update user last name\"},
         {\"command\": \"create_discount\", \"description\": \"Create discount\"},
         {\"command\": \"cancel_discount\", \"description\": \"Cancel discount\"},
         {\"command\": \"view_discount\", \"description\": \"View discount status\"},
         {\"command\": \"process_delivery\", \"description\": \"Process wholesale deliveries\"},
         {\"command\": \"process_labeling\", \"description\": \"Complete labeling process\"},
         {\"command\": \"send_delivery_overviews\", \"description\": \"Send delivery overviews\"},
         {\"command\": \"process_payment\", \"description\": \"Mark customers as paid\"},
         {\"command\": \"failed_notifications\", \"description\": \"View failed delivery notifications\"},
         {\"command\": \"delete_old_orders\", \"description\": \"Delete old cancelled and completed orders (7+ days)\"},
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