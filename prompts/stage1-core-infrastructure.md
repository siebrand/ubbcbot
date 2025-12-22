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

## DEPLOYMENT & INTEGRATION:
- Use AWS SAM for infrastructure deployment (template.yaml + samconfig.toml)
- Set Telegram webhook to API Gateway endpoint with secret validation
- Environment-specific bot tokens stored in Parameter Store
- Test environment messages prefixed with "TEST - "
- Webhook endpoint: POST /webhook with Lambda proxy integration
- Bot registered with @BotFather for test and production environments

## RESOURCE NAMING & TAGGING:
- All resources follow naming convention: `ubbc-bot-{environment}-{resource-type}`
- Required tags: Project, Environment, Owner, CostCenter, Application, ManagedBy
- Lambda: `ubbc-bot-test-webhook-handler`, `ubbc-bot-prod-webhook-handler`
- DynamoDB: `ubbc-bot-test-offers`, `ubbc-bot-prod-customers`
- S3: `ubbc-bot-test-{account-id}-images`, `ubbc-bot-prod-{account-id}-images`
- API Gateway: `ubbc-bot-test-api`, `ubbc-bot-prod-api`
- Parameter Store: `/ubbc-bot/test/telegram-token`, `/ubbc-bot/prod/telegram-token`

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

**Deployment Requirements:**
- DR-001: AWS SAM infrastructure deployment
- DR-002: Environment management (test/prod)
- DR-004: Parameter Store configuration
- IR-001: SAM template structure
- IR-002: Webhook endpoint configuration
- IR-003: Bot token management
- IR-004: Deployment commands setup
- IR-005: Environment configuration files
- IR-006: Resource naming convention
- IR-007: Required AWS tags

**Telegram Integration:**
- TI-001: Bot registration with @BotFather
- TI-002: Webhook configuration to API Gateway
- TI-003: Webhook security validation
- TI-006: Group integration setup

**Business Rules:**
- BR-001 through BR-010: Core order and box validation

**Security Requirements:**
- SR-001: Admin access control (ID: 15005473)
- SR-002: Customer data privacy
- SR-014: Webhook security
- SR-015: Token security

## SUCCESS CRITERIA:
After Stage 1, the system must:
✓ Deploy via AWS SAM to test and production environments
✓ Accept Telegram webhooks with proper validation
✓ Accept admin commands for supplier and offer management
✓ Process customer orders with proper validation
✓ Track box status and capacity
✓ Store all data persistently in DynamoDB
✓ Restrict admin functions to authorized user
✓ All AWS resources follow naming convention and have required tags
✓ Environment-specific configuration working correctly