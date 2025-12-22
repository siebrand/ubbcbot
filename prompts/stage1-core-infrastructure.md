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