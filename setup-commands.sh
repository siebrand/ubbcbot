#!/bin/bash

# UBBC Bot Commands Setup Script
#
# Registers three command menus (see telegram-commands.json) so Telegram only suggests what works where:
#   group     in group chats                  (all_group_chats)
#   customer  in private chats, and the default (all_private_chats, default)
#   admin     in the private chat of the admin only (chat, with the admin's user ID from samconfig.toml)
#
# Usage: ./setup-commands.sh <test|prod>
# DRY_RUN=1 ./setup-commands.sh <test|prod> prints the Telegram calls instead of making them (used by the tests)
set -e

ENVIRONMENT=${1:-test}

if [ "$ENVIRONMENT" != "test" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "Usage: $0 <environment>"
    echo "Environment: test or prod"
    exit 1
fi

if ! command -v jq > /dev/null; then
    echo "jq is required"
    exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
COMMANDS_FILE="$DIR/telegram-commands.json"

echo "🤖 Setting up bot commands for $ENVIRONMENT environment..."

# Get bot token
if [ -n "$DRY_RUN" ]; then
    TELEGRAM_TOKEN="dry-run"
else
    TELEGRAM_TOKEN=$(aws ssm get-parameter \
        --name "/ubbc-bot/$ENVIRONMENT/telegram-bot-token" \
        --with-decryption \
        --query 'Parameter.Value' \
        --output text)
fi

# The admin gets the admin menu in the private chat with the bot
ADMIN_USER_ID=$(sed -n "s/.*Environment=$ENVIRONMENT AdminUserId=\([0-9][0-9]*\).*/\1/p" "$DIR/samconfig.toml" | head -n 1)
if [ -z "$ADMIN_USER_ID" ]; then
    echo "No AdminUserId for $ENVIRONMENT in samconfig.toml"
    exit 1
fi

# Default group ID for the command scopes that were set per group before
if [ "$ENVIRONMENT" = "test" ]; then
    DEFAULT_GROUP_ID="-1003399818858"
else
    DEFAULT_GROUP_ID="-1001662432692"
fi

api() {
    local method="$1" payload="$2"
    if [ -n "$DRY_RUN" ]; then
        echo "DRY_RUN $method $payload"
        return
    fi
    curl -s -X POST --max-time 20 "https://api.telegram.org/bot$TELEGRAM_TOKEN/$method" \
         -H "Content-Type: application/json" \
         -d "$payload" | jq .
}

delete_menu() {
    api deleteMyCommands "$(jq -cn --argjson scope "$1" '{scope: $scope}')"
}

set_menu() {
    local menu="$1" scope="$2"
    api setMyCommands "$(jq -cn \
        --argjson commands "$(jq -c ".$menu" "$COMMANDS_FILE")" \
        --argjson scope "$scope" \
        '{commands: $commands, scope: $scope}')"
}

# These scopes win over the group menu in a group, so they must not exist
echo "🗑️  Removing old group overrides..."
delete_menu "$(jq -cn --argjson id "$DEFAULT_GROUP_ID" '{type: "chat_administrators", chat_id: $id}')"
delete_menu "$(jq -cn --argjson id "$DEFAULT_GROUP_ID" '{type: "chat", chat_id: $id}')"
delete_menu '{"type": "all_chat_administrators"}'

echo ""
echo "👥 Setting the group menu..."
set_menu group '{"type": "all_group_chats"}'

echo ""
echo "🧑 Setting the customer menu (private chats and default)..."
set_menu customer '{"type": "all_private_chats"}'
set_menu customer '{"type": "default"}'

echo ""
echo "🛠️  Setting the admin menu (private chat of the admin only)..."
set_menu admin "$(jq -cn --argjson id "$ADMIN_USER_ID" '{type: "chat", chat_id: $id}')"

echo ""
echo "✅ Bot commands configured successfully!"
