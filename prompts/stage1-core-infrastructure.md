# Stage 1: Core Bot Infrastructure (Foundation)

Implement a Telegram beer ordering bot with AWS serverless architecture. Focus on core functionality:

## CORE REQUIREMENTS:
- Admin user ID: 15005473 (siebrand)
- AWS Lambda + DynamoDB + API Gateway + S3 architecture
- Basic offer creation with supplier tracking
- Order placement and box assignment logic
- Customer registration and order history
- Minimal viable bot commands for testing

## CRITICAL BUSINESS RULES:
- Wholesale box sizes: 1,2,6,8,10,12,15,16,18,20,24 units
- Auto-create new boxes when capacity reached
- Track box status: open → minimum_reached → full → ordered → delivered
- Validate orders against available capacity

## ESSENTIAL COMMANDS:
Admin: /add_supplier, /create_offer, /list_offers, /box_status
Customer: /start, /order, /my_orders

Use the exact data models from requirements.md and follow aws-architecture.md specifications.

## REQUIREMENTS TO IMPLEMENT:
**Functional Requirements:**
- FR-001: Basic offer creation with supplier tracking
- FR-005: Customer order placement
- FR-006: Order validation (capacity, limits, status)
- FR-007: Order assignment to boxes
- FR-008: Box fulfillment tracking
- FR-009: Automatic box creation
- FR-010: Box status tracking
- FR-011: Customer registration
- FR-012: View active orders
- FR-017: Supplier registration
- FR-018: Update supplier information

**Technical Requirements:**
- TR-001: Telegram Bot API integration
- TR-002: Database storage (DynamoDB)
- TR-003: Python implementation
- TR-004: Core data storage

**Business Rules:**
- BR-001 through BR-010: Core order and box validation

**Security Requirements:**
- SR-001: Admin access control (ID: 15005473)
- SR-002: Customer data privacy

## SUCCESS CRITERIA:
After Stage 1, the system must:
✓ Accept admin commands for supplier and offer management
✓ Process customer orders with proper validation
✓ Track box status and capacity
✓ Store all data persistently in DynamoDB
✓ Restrict admin functions to authorized user