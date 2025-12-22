# Stage 2: Advanced Features (Business Logic)

Extend the existing Telegram bot with advanced business features:

## ADD TO EXISTING SYSTEM:
- Multi-group publishing with scheduling (immediate + delayed)
- Discount system with CE(S)T timezone support and auto-notifications
- Image upload and management (S3 + CloudFront)
- Enhanced supplier management
- Group membership validation for order confirmations
- Admin proxy ordering for customers

## DISCOUNT FEATURES:
- /discount_mode command with percentage and end time
- Auto-notifications: start, 10-min warning, expiry
- Apply to all open offers except excluded ones
- Record discount percentage in orders

## IMAGE FEATURES:
- Main offer images + option-specific images (A,B,C)
- S3 storage with CloudFront CDN
- Admin-only upload restrictions

Maintain all existing functionality while adding these features.