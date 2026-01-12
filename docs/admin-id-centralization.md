# Admin User ID Centralization - Summary

## Changes Made

### 1. Centralized Configuration
**File:** `src/config.py` (NEW)
- Single source of truth for ADMIN_USER_ID
- Reads from environment variable `ADMIN_USER_ID`
- Default value: `0` (dummy, forces explicit configuration)

### 2. Infrastructure Configuration
**File:** `template.yaml`
- Added `AdminUserId` parameter (NoEcho for security)
- Removed hardcoded value `'15005473'`
- Uses `!Ref AdminUserId` in environment variables

**File:** `samconfig.toml`
- Added `AdminUserId=<YOUR_TELEGRAM_USER_ID>` placeholder to parameter overrides
- Requires manual configuration before deployment

### 3. Application Code
**File:** `src/services/bot_service.py`
- Imports `ADMIN_USER_ID` from `config` module
- Removed hardcoded fallback value

### 4. Documentation
**Files Updated:** All `.md` files
- Replaced all occurrences of `15005473` with `<ADMIN_USER_ID>` placeholder
- Updated deployment instructions to include admin ID configuration step
- Removed specific admin ID references from command descriptions

**Files affected:**
- README.md
- .amazonq/rules/project-requirements.md
- docs/*.md (all documentation files)
- prompts/*.md
- requirements.md
- tests/end-to-end-test-plan.md
- aws-architecture.md

## Configuration Required

### Before Deployment

1. **Find your Telegram user ID:**
   - Send a message to @userinfobot on Telegram
   - Note the user ID number

2. **Update samconfig.toml:**
   ```toml
   [test.deploy.parameters]
   parameter_overrides = "Environment=test AdminUserId=YOUR_TELEGRAM_USER_ID"
   
   [prod.deploy.parameters]
   parameter_overrides = "Environment=prod AdminUserId=YOUR_TELEGRAM_USER_ID"
   ```

3. **Deploy:**
   ```bash
   ./deploy.sh test
   ```

## Security Improvements

✅ Admin ID no longer hardcoded in 87 locations  
✅ Admin ID not exposed in documentation  
✅ Admin ID configured per deployment (test/prod can have different admins)  
✅ Admin ID marked as `NoEcho` in CloudFormation (not visible in console)  
✅ Single source of truth in code (`config.py`)  

## Migration Notes

- Existing deployments will continue to work (environment variable already set)
- New deployments require `AdminUserId` parameter in samconfig.toml
- No code changes needed in handlers (they already use `self.admin_user_id`)

## Verification

After deployment, verify admin ID is set correctly:
```bash
# Check Lambda environment variables
aws lambda get-function-configuration \
  --function-name ubbc-bot-test-webhook-handler \
  --query 'Environment.Variables.ADMIN_USER_ID'
```

Should return your Telegram user ID (not 0).
