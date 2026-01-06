# UBBC Bot Scripts

This directory contains utility scripts for analyzing and managing the UBBC Bot data.

## group_customer_analysis.py

Analyzes the differences between registered customers and members of the default Telegram group.

### Usage

```bash
# Analyze test environment (default)
python3 scripts/group_customer_analysis.py

# Analyze production environment
python3 scripts/group_customer_analysis.py --env prod
```

### What it does

**A) Lists customers not in the default group**
- Shows registered customers who are not visible as group members
- Includes customer details: name, username, status, registration date

**B) Lists group members not registered as customers**
- Shows group administrators who haven't registered with the bot
- Limited to administrators due to Telegram API privacy restrictions

### Setup

```bash
# Activate virtual environment
source test_env/bin/activate

# Install dependencies
pip install -r scripts/requirements.txt
```

### Requirements

- AWS CLI configured with appropriate permissions
- Access to Parameter Store for bot tokens
- DynamoDB read permissions for customer tables

### Limitations

- Telegram Bot API only provides access to:
  - Group administrators
  - Users who have interacted with the bot
- Regular group members are not accessible via API for privacy reasons
- For complete analysis, manual group inspection would be needed

### Output

The script provides:
- Count of registered customers
- Count of accessible group members
- Detailed lists of mismatches
- Summary statistics
- Explanation of API limitations