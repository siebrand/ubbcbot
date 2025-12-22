#!/bin/bash

# UBBC Bot Deployment Script
set -e

ENVIRONMENT=${1:-test}
TELEGRAM_TOKEN=${2}

if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "Usage: $0 <environment> <telegram_token>"
    echo "Environment: test or prod"
    exit 1
fi

echo "🚀 Deploying UBBC Bot to $ENVIRONMENT environment..."

# Build and deploy
echo "📦 Building SAM application..."
sam build

echo "🚀 Deploying to $ENVIRONMENT..."
sam deploy \
    --config-env $ENVIRONMENT \
    --parameter-overrides "Environment=$ENVIRONMENT TelegramToken=$TELEGRAM_TOKEN" \
    --no-confirm-changeset

# Get webhook URL
WEBHOOK_URL=$(aws cloudformation describe-stacks \
    --stack-name "ubbc-bot-$ENVIRONMENT" \
    --query 'Stacks[0].Outputs[?OutputKey==`WebhookUrl`].OutputValue' \
    --output text)

echo "✅ Deployment complete!"
echo "📡 Webhook URL: $WEBHOOK_URL"
echo ""
echo "Next steps:"
echo "1. Set webhook in Telegram: curl -X POST \"https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook\" -d \"url=$WEBHOOK_URL\""
echo "2. Test with /start command in Telegram"