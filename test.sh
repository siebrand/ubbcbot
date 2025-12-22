#!/bin/bash

# UBBC Bot Test Script
ENVIRONMENT=${1:-test}
BOT_TOKEN=${2}

if [ -z "$BOT_TOKEN" ]; then
    echo "Usage: $0 <environment> <bot_token>"
    exit 1
fi

echo "🧪 Testing UBBC Bot in $ENVIRONMENT environment..."

# Get webhook info
echo "📡 Checking webhook status..."
curl -s "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo" | jq .

# Test webhook endpoint
WEBHOOK_URL=$(aws cloudformation describe-stacks \
    --stack-name "ubbc-bot-$ENVIRONMENT" \
    --query 'Stacks[0].Outputs[?OutputKey==`WebhookUrl`].OutputValue' \
    --output text)

echo "🔗 Webhook URL: $WEBHOOK_URL"

# Test with sample update
echo "📤 Testing webhook endpoint..."
curl -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d '{
        "update_id": 123,
        "message": {
            "message_id": 1,
            "from": {
                "id": 15005473,
                "first_name": "Test",
                "username": "testuser"
            },
            "chat": {
                "id": 15005473,
                "type": "private"
            },
            "date": 1640995200,
            "text": "/start"
        }
    }'

echo ""
echo "✅ Test complete. Check CloudWatch logs for details."