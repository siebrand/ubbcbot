# User Client Setup (Telethon)

This setup allows the bot to send messages FROM your admin Telegram account TO customers.

## Prerequisites

1. **Telegram API Credentials**
   - Go to https://my.telegram.org/apps
   - Log in with your admin phone number (you'll receive a verification code)
   - Click "API development tools"
   - If you don't have an app yet:
     - Fill in "App title" (e.g., "UBBC User Client")
     - Fill in "Short name" (e.g., "ubbc_client")
     - Platform: Select "Other"
     - Description: (e.g., "User client for UBBC bot to send messages from admin account")
     - Click "Create application"
   - Save your `api_id` (numeric, e.g., 12345678)
   - Save your `api_hash` (alphanumeric string, e.g., "0123456789abcdef0123456789abcdef")
   - **Important**: These credentials are for YOUR account, not the bot

## Setup Steps

### 1. Create Virtual Environment

```bash
python3.14 -m venv setup_venv
source setup_venv/bin/activate  # On Windows: setup_venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r setup_requirements.txt
```

### 3. Run Setup Script

For test environment:
```bash
python setup_user_client.py test
```

For production environment:
```bash
python setup_user_client.py prod
```

### 4. Follow Prompts

The script will:
1. Ask for your API ID and API Hash
2. Store them in AWS Parameter Store
3. Ask for your phone number (with country code, e.g., +1234567890)
4. Send you a verification code via Telegram
5. Ask you to enter the code
6. Store the authenticated session in Parameter Store

### 5. Deploy

After setup, deploy the updated infrastructure:

```bash
./deploy.sh test  # or prod
```

### 6. Cleanup

```bash
deactivate  # Exit virtual environment
rm -rf setup_venv  # Optional: remove virtual environment
```

## Testing

Once deployed, test the user message functionality:

```bash
# Send test message to yourself
/test_user_message YOUR_USER_ID Test message from admin account

# Send test message to another user
/test_user_message CUSTOMER_USER_ID Hello from admin!
```

## Security Notes

- Your session is stored encrypted in AWS Parameter Store
- The session allows sending messages as your account
- Keep your API credentials secure
- Session may need periodic re-authentication (Telegram will notify you)

## Troubleshooting

**"User client not authorized" error:**
- Re-run the setup script to re-authenticate
- Check that the session parameter exists in Parameter Store

**Lambda timeout:**
- First invocation may be slow (cold start + Telethon connection)
- Subsequent invocations should be faster

**Rate limits:**
- User accounts have stricter rate limits than bots
- Avoid sending too many messages in quick succession
