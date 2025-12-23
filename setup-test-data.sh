#!/bin/bash

# Test Data Setup Script
# Creates a text file with commands to copy/paste

ENVIRONMENT=${1:-test}

echo "🚀 Generating test data commands for $ENVIRONMENT environment..."

# Create commands file
cat > test-commands.txt << 'EOF'
/add_supplier HD
/add_supplier DK
/add_supplier BW
/add_supplier DM
/create_offer HD Hopduvel Tripel 4.50 12
/create_offer DK De Koninck Bolleke 2.80 24
/create_offer BW West Coast IPA 5.20 6
/create_offer DM Duvel Golden Ale 3.90 12
/create_offer HD Hopduvel Saison 4.20 12
/create_offer BW Hazy IPA 5.50 6
/create_offer HD Limited Edition Barrel Aged 25.00 1
/create_offer DK Vintage Reserve 18.50 2
EOF

echo "✅ Commands saved to test-commands.txt"
echo "📋 Copy and paste each line individually into your Telegram chat:"
echo ""
cat test-commands.txt