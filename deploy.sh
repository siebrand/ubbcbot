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

# Run tests first
echo "🧪 Running test suite..."
if [ ! -d "test_env" ]; then
    echo "Creating test virtual environment..."
    python3 -m venv test_env
fi
source test_env/bin/activate
if ! pip show pytest >/dev/null 2>&1; then
    echo "Installing test dependencies..."
    pip install -r tests/requirements.txt
fi

# Set PYTHONPATH for imports
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"

# Run refactoring unit tests
echo "Running refactoring unit tests..."
if ! python -m unittest discover -s tests/handlers/admin -p "test_*.py" -v; then
    echo "❌ Refactoring tests failed! Deployment aborted."
    deactivate
    exit 1
fi

# Run legacy tests
echo "Running legacy tests..."
if ! python tests/run_tests.py; then
    echo "❌ Legacy tests failed! Deployment aborted."
    deactivate
    exit 1
fi

# Run pytest tests
echo "Running pytest tests..."
PYTEST_FILES="
    tests/test_command_routing.py
    tests/test_callback_routing.py
    tests/test_customer_orders.py
    tests/test_box_status_manager.py
    tests/test_box_deletion_service.py
    tests/test_mark_paid_pagination.py
    tests/test_offer_cache.py
    tests/test_csv_parser.py
    tests/test_import_handler.py
"
if ! python -m pytest $PYTEST_FILES -v; then
    echo "❌ Pytest tests failed! Deployment aborted."
    deactivate
    exit 1
fi

deactivate
echo "✅ All tests passed!"
echo ""

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
curl -s -X POST --max-time 20 "https://api.telegram.org/bot$TELEGRAM_TOKEN/setWebhook" \
     -d "url=$WEBHOOK_URL" | jq .

echo ""
echo "🤖 Setting up bot commands..."
./setup-commands.sh $ENVIRONMENT

echo ""
echo "✅ Setup complete! Next steps:"
echo "1. Test with /start command in Telegram"
echo "2. Verify webhook status: curl \"https://api.telegram.org/bot$TELEGRAM_TOKEN/getWebhookInfo\""
echo "3. Run tests locally: source test_env/bin/activate && export PYTHONPATH=\$(pwd)/src:\$PYTHONPATH && python -m unittest discover -s tests/handlers/admin -p 'test_*.py' -v && python tests/run_tests.py && python -m pytest tests/test_customer_orders.py tests/test_mark_paid_pagination.py -v"
echo ""
echo "🕐 Deployment completed at: $(date)"