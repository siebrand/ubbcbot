# New User Authorization Notification Feature

## Overview
The UBBC Bot now automatically sends notifications to the admin (Siebrand, user ID: 15005473) whenever a new user registers and is pending authorization.

## How It Works

### User Registration Flow
1. New user sends `/start` command to the bot
2. Bot automatically registers the user in the database with `UNAUTHORIZED` status
3. Bot immediately sends a notification to the admin about the pending authorization
4. User receives the standard "pending approval" message
5. Admin can review pending users with `/pending_users` command

### Notification Message Format
The admin receives a message in this format:

**English:**
```
🔔 New user authorization pending:

👤 John Doe
📱 @johndoe
🆔 ID: 123456789

Use /pending_users to review.
```

**Dutch:**
```
🔔 Nieuwe gebruiker wacht op autorisatie:

👤 John Doe
📱 @johndoe
🆔 ID: 123456789

Gebruik /pending_users om te beoordelen.
```

### Edge Cases Handled
- Users without usernames show "no_username"
- Users without last names show only first name
- Users with minimal data are handled gracefully
- Notification failures are logged but don't break the registration process

## Implementation Details

### Files Modified
- `src/services/bot_service.py`: Added notification logic to user registration
- `src/translations/en.json`: Added English notification message
- `src/translations/nl.json`: Added Dutch notification message

### Key Components
- `_notify_admin_new_user_pending()`: New method that sends the notification
- `new_user_pending_notification`: New translation key for the message
- Integration with existing translation system for proper language handling

### Testing
- Added comprehensive tests in `tests/test_new_user_notification.py`
- Updated existing user management tests
- All tests pass successfully

## Benefits
- **Immediate Awareness**: Admin is notified instantly when new users register
- **Faster Response**: Reduces time between user registration and approval
- **Better User Experience**: Users get approved faster, improving onboarding
- **Audit Trail**: All notifications are logged for tracking purposes

## Configuration
- Admin user ID is configured via environment variable `ADMIN_USER_ID` (default: 15005473)
- Notifications respect the test/production environment prefixes
- Uses the existing Telegram token and messaging infrastructure

## Future Enhancements
- Could add notification preferences (email, different chat, etc.)
- Could include user statistics in notifications
- Could add batch notifications for multiple pending users