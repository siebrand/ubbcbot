# UBBC Bot Feature Ideas

## Subscription System for New Offers
**Status**: Idea  
**Priority**: Medium

### Description
Allow users to subscribe/unsubscribe to receive private messages when new offers are published.

### Implementation
- Add `notification_preferences` field to Customer model (default: enabled)
- Add `/subscribe` and `/unsubscribe` commands
- Modify offer creation to send PMs to subscribed users
- Add subscription status to `/start` help text

### Commands
- `/subscribe` - Enable new offer notifications
- `/unsubscribe` - Disable new offer notifications

### Database Changes
- Add `notifications_enabled` boolean field to customers table (default: true)

### Benefits
- Users get immediate notification of new offers
- Reduces need to check group constantly
- Optional feature - users can opt out