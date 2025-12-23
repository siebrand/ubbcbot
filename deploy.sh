#!/bin/bash

# UBBC Bot Deployment Script
set -e

# Disable SAM telemetry
export SAM_CLI_TELEMETRY=0

ENVIRONMENT=${1:-test}

if [ "$ENVIRONMENT" != "test" ] && [ "$ENVIRONMENT" != "prod" ]; then
    echo "Usage: $0 <environment>"
    echo "Environment: test or prod"
    exit 1
fi

echo "🚀 Deploying UBBC Bot to $ENVIRONMENT environment..."

# Verify token exists in Parameter Store
echo "🔍 Checking for bot token in Parameter Store..."
if ! aws ssm get-parameter --name "/ubbc-bot/$ENVIRONMENT/telegram-bot-token" --with-decryption >/dev/null 2>&1; then
    echo "❌ Bot token not found in Parameter Store: /ubbc-bot/$ENVIRONMENT/telegram-bot-token"
    echo "Please store the token first:"
    echo "aws ssm put-parameter --name \"/ubbc-bot/$ENVIRONMENT/telegram-bot-token\" --value \"YOUR_BOT_TOKEN\" --type \"SecureString\""
    exit 1
fi

# Build and deploy
echo "📦 Building SAM application..."
sam build

echo "🚀 Deploying to $ENVIRONMENT..."
sam deploy \
    --config-env $ENVIRONMENT \
    --parameter-overrides "Environment=$ENVIRONMENT" \
    --resolve-s3 \
    --capabilities CAPABILITY_IAM \
    --no-confirm-changeset

# Get webhook URL and token for final setup
WEBHOOK_URL=$(aws cloudformation describe-stacks \
    --stack-name "ubbc-bot-$ENVIRONMENT" \
    --query 'Stacks[0].Outputs[?OutputKey==`WebhookUrl`].OutputValue' \
    --output text)

TELEGRAM_TOKEN=$(aws ssm get-parameter \
    --name "/ubbc-bot/$ENVIRONMENT/telegram-bot-token" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text)

echo "✅ Deployment complete!"
echo "📡 Webhook URL: $WEBHOOK_URL"
echo ""
echo "🔗 Setting Telegram webhook..."
curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook" \
     -d "url=$WEBHOOK_URL" | jq .

echo ""
echo "🤖 Setting up bot commands..."
./setup-commands.sh $ENVIRONMENT

echo ""
echo "✅ Setup complete! Next steps:"
echo "1. Test with /start command in Telegram"
echo "2. Verify webhook status: curl \"https://api.telegram.org/bot$TELEGRAM_TOKEN/getWebhookInfo\""