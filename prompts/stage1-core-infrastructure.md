# Stage 1: Core Bot Infrastructure (Foundation)

Implement a Telegram beer ordering bot with AWS serverless architecture. Focus on core functionality:

## CORE REQUIREMENTS:
- ✅ Admin user ID: 15005473 (siebrand)
- ✅ AWS Lambda + DynamoDB + API Gateway + S3 architecture
- ✅ Basic offer creation with supplier tracking
- ✅ Order placement and box assignment logic
- ✅ Customer registration and order history
- ✅ Minimal viable bot commands for testing

## CRITICAL BUSINESS RULES:
- ✅ Wholesale box sizes: 1,2,6,8,10,12,15,16,18,20,24 units
- ✅ Auto-create new boxes when capacity reached in a pre-ordered state of the offer
- ✅ Track box status: open → minimum_reached → full → ordered → delivered
- ✅ Validate orders against available capacity

## DEPLOYMENT & INTEGRATION:
- ✅ Use AWS SAM for infrastructure deployment (template.yaml + samconfig.toml)
- ✅ Set Telegram webhook to API Gateway endpoint with secret validation
- ✅ Environment-specific bot tokens stored in Parameter Store
- ✅ Test environment messages prefixed with "TEST - "
- ✅ Webhook endpoint: POST /webhook with Lambda proxy integration
- ✅ Bot registered with @BotFather for test and production environments
- ✅ Executable scripts must have git executable flag: `git update-index --chmod=+x script.sh`

## RESOURCE NAMING & TAGGING:
- ✅ All resources follow naming convention: `ubbc-bot-{environment}-{resource-type}`
- Required tags: , Environment, Owner, CostCenter, Application, ManagedBy
- ✅ Lambda: `ubbc-bot-test-webhook-handler`, `ubbc-bot-prod-webhook-handler`
- ✅ DynamoDB: `ubbc-bot-test-offers`, `ubbc-bot-prod-customers`
- ✅ S3: `ubbc-bot-test-{account-id}-images`, `ubbc-bot-prod-{account-id}-images`
- ✅ API Gateway: `ubbc-bot-test-api`, `ubbc-bot-prod-api`
- ✅ Parameter Store: `/ubbc-bot/test/telegram-token`, `/ubbc-bot/prod/telegram-token`

## ✅ ESSENTIAL COMMANDS:

### Admin Commands (User ID: 15005473):
**Test Environment Only:**
- `/setup_test_data` - Setup test suppliers and offers

**Supplier Management:**
- `/add_supplier <name>` - Add new supplier
- `/retire_supplier <name>` - Retire supplier (no longer available for new offers)
- `/list_suppliers` - View all registered suppliers (paginated)
- `/edit_supplier <name>` - Edit supplier details with inline keyboard

**Offer Management:**
- `/create_offer <supplier_name> <name> <price> <box_size>` - Create beer offer
- `/cancel_offer <offer_id>` - Cancel offer and all related orders (button confirmation)
- `/edit_offer <offer_id>` - Edit offer details with inline keyboard
- `/add_box <offer_id>` - Add single box to offer (updates sold out offers to active)
- `/box_status` - View box status and capacity (paginated)
- `/fulfill_offer <offer_id>` - Start fulfillment process (button confirmation)

**Order Management:**
- `/order_for <username> <offer_id> [quantity]` - Place order for another user (10-unit admin limit)
- `/cancel_order <order_id>` - Cancel customer order (button confirmation)
- `/user_orders <username>` - View orders for specific user
- `/all_orders [active|cancelled|ordered|all]` - Download CSV of all orders (default: active)

**User Management:**
- `/pending_users` - View users awaiting approval (paginated with approve/reject buttons)
- `/list_customers` - View all customers (paginated with status filtering)
- `/approve_user <name_or_username>` - Approve user
- `/reject_user <name_or_username>` - Reject user
- `/user_status <name_or_username>` - Check user status
- `/update_user <username> <new_first_name> [new_last_name]` - Update customer name

### Customer Commands:
**General:**
- `/start` - Register and view help

**Orders:**
- `/order <offer_id> [quantity]` - Place order (5-unit customer limit)
- `/confirm_order <offer_id> <quantity>` - Confirm duplicate order
- `/my_orders [id]` - View personal orders (add 'id' to show order IDs)
- `/list_offers` - View available offers

**Notifications:**
- `/subscribe` - Subscribe to new offer notifications
- `/unsubscribe` - Unsubscribe from offer notifications

Use the exact data models from requirements.md and follow aws-architecture.md specifications.

## ✅ BUSINESS LOGIC IMPLEMENTED:
- **Order Limits:** 5-unit customer limit, 10-unit admin limit for `/order_for`
- **Duplicate Order Handling:** Warns customers about existing orders before placing new ones
- **Box Management:** Auto-create new boxes when capacity reached, track status transitions
- **Notification System:** Automatic cleanup of notification messages for sold out and cancelled offers
- **Order Cancellation:** Admin-only with confirmation for full boxes, automatic inventory correction
- **Fulfillment Process:** Two-step fulfillment with order prioritization (oldest first)
- **Sold Out Notifications:** Group notifications include "SOLD OUT" status when last item ordered
- **User Authorization:** Three-tier approval system (unauthorized, approved, rejected)
- **Supplier Management:** Active/retired status with validation for new offers
- **CSV Export:** Complete order data export with filtering by status
- **Test Data Setup:** Automated test environment data creation
- **Subscription Management:** Opt-in/opt-out notification system with batch delivery
- **Order Aggregation:** Smart grouping by offer, price, and status in customer views

## ✅ REQUIREMENTS IMPLEMENTED:
**Functional Requirements:**
- ✅ FR-001: Basic offer creation with supplier tracking
- ✅ FR-005: Customer order placement
- ✅ FR-006: Order validation (capacity, limits, status)
- ✅ FR-007: Order assignment to boxes
- ✅ FR-008: Box fulfillment tracking
- ✅ FR-009: Automatic box creation
- ✅ FR-010: Box status tracking
- ✅ FR-011: Customer registration
- ✅ FR-012: View active orders
- ✅ FR-017: Supplier registration
- ✅ FR-018: Update supplier information
- ✅ FR-019: Order cancellation with inventory correction
- ✅ FR-020: User authorization management
- ✅ FR-021: Notification subscription system
- ✅ FR-022: CSV order export functionality

**Technical Requirements:**
- ✅ TR-001: Telegram Bot API integration
- ✅ TR-002: Database storage (DynamoDB)
- ✅ TR-003: Python implementation
- ✅ TR-004: Core data storage
- ✅ TR-005: Webhook security validation
- ✅ TR-006: Environment-specific configuration

**Deployment Requirements:**
- ✅ DR-001: AWS SAM infrastructure deployment
- ✅ DR-002: Environment management (test/prod)
- ✅ DR-004: Parameter Store configuration
- ✅ IR-001: SAM template structure
- ✅ IR-002: Webhook endpoint configuration
- ✅ IR-003: Bot token management
- ✅ IR-004: Deployment commands setup
- ✅ IR-005: Environment configuration files
- ✅ IR-006: Resource naming convention
- ✅ IR-007: Required AWS tags

**Telegram Integration:**
- ✅ TI-001: Bot registration with @BotFather
- ✅ TI-002: Webhook configuration to API Gateway
- ✅ TI-003: Webhook security validation
- ✅ TI-006: Group integration setup
- ✅ TI-007: Inline keyboard support
- ✅ TI-008: Message cleanup automation

**Business Rules:**
- ✅ BR-001 through BR-010: Core order and box validation
- ✅ BR-011: Order limits enforcement
- ✅ BR-012: Duplicate order handling
- ✅ BR-013: Fulfillment process workflow

**Security Requirements:**
- ✅ SR-001: Admin access control (ID: 15005473)
- ✅ SR-002: Customer data privacy
- ✅ SR-014: Webhook security
- ✅ SR-015: Token security

## ✅ SUCCESS CRITERIA - STAGE 1 COMPLETE:
After Stage 1, the system must:

- ✅ Deploy via AWS SAM to test and production environments
- ✅ Accept Telegram webhooks with proper validation
- ✅ Accept admin commands for supplier and offer management
- ✅ Process customer orders with proper validation
- ✅ Track box status and capacity
- ✅ Store all data persistently in DynamoDB
- ✅ Restrict admin functions to authorized user
- ✅ All AWS resources follow naming convention and have required tags
- ✅ Environment-specific configuration working correctly

## ADDITIONAL FEATURES IMPLEMENTED:
- ✅ Advanced order management with cancellation and fulfillment workflows
- ✅ User authorization system with approval/rejection workflow
- ✅ Notification subscription system with automatic cleanup
- ✅ CSV export functionality for order data analysis
- ✅ Test data setup for development environment
- ✅ Comprehensive error handling and validation
- ✅ Inline keyboard support for better user experience
- ✅ Group integration with order notifications
- ✅ Duplicate order detection and confirmation
- ✅ Order aggregation and smart display formatting

**Stage 1 Status: ✅ COMPLETE - Ready for Stage 2 Advanced Features**