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

## REQUIREMENTS TO IMPLEMENT:
**Functional Requirements:**
- FR-002: Post offers with text and images to groups
- FR-003: Schedule offers for delayed publishing
- FR-004: Update offer details including images
- FR-013: Customer order cancellation
- FR-014: Configure multiple groups
- FR-015: Scheduled publishing system
- FR-019: View supplier order history
- FR-020: Track orders per supplier
- FR-021: Activate discount mode
- FR-022: Automatic discount notifications
- FR-023: Apply discount pricing to orders
- FR-034: Public order confirmation with membership logic
- FR-035: Channel membership validation
- FR-036: Admin proxy ordering

**Technical Requirements:**
- TR-007: Image storage and retrieval
- TR-008: Support image formats (JPEG, PNG, WebP)
- TR-012: Efficient image handling
- TR-013: Image compression
- TR-014: Scheduled notification system
- TR-015: CE(S)T timezone support

**Business Rules:**
- BR-011 through BR-031: Group management, image handling, discount rules

## SUCCESS CRITERIA:
After Stage 2, the system must:
✓ Handle multi-group publishing with scheduling
✓ Process discount periods with automatic notifications
✓ Store and serve images via S3/CloudFront
✓ Validate channel membership for order confirmations
✓ Support admin proxy ordering with notifications