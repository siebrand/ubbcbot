# Telegram Beer Ordering Bot - Requirements Document

**License:** MIT - This document and associated architecture documentation are publicly available.

## 1. Project Overview

### 1.1 Purpose
Create a Telegram bot to automate beer order registration for a beer sales channel, managing customer orders against wholesale box quantities and profit margins.

### 1.2 Business Context
- Beer sold through multiple Telegram groups/channels
- Orders placed against wholesale boxes (e.g., 12-unit boxes)
- Minimum order quantities required to break even (e.g., 10 orders for 20% profit margin)
- Multiple offer options per post (labeled A, B, C, etc.)
- Exclusive member groups with early/exclusive access to offers
- Scheduled publishing from exclusive to general groups

## 2. Functional Requirements

### 2.1 Offer Management
- **FR-001**: Admin can create offers with the following attributes:
  - Offer ID (auto-generated)
  - Supplier name (from registered suppliers)
  - Beer name/description
  - Price per unit
  - Wholesale box size (e.g., 12 units)
  - Minimum quantity needed for breakeven
  - Maximum quantity (optional)
  - Multiple options (A, B, C) if applicable
  - Main offer image (optional)
  - Per-option images (optional)
  - Target groups (default + additional groups)
  - Publishing schedule (immediate or delayed)
  - Offer status (active/inactive/completed)

- **FR-002**: Admin can post offers with text and images to specific Telegram groups
- **FR-003**: Admin can schedule offers to publish in additional groups after delay
- **FR-004**: Admin can update offer details including images
- **FR-005**: Admin can close/deactivate offers

### 2.2 Order Processing
- **FR-005**: Customers can place orders by responding to offers
- **FR-006**: Bot validates order against:
  - Available quantity
  - Minimum/maximum limits
  - Offer status (active)
- **FR-007**: Bot assigns orders to specific wholesale boxes
- **FR-008**: Bot tracks order fulfillment progress per box
- **FR-034**: System sends public order confirmation in default channel:
  - Shows customer name if user is member of default channel
  - Shows "anonymous" if user is not member of default channel
  - Includes pre-order disclaimer that orders are not guaranteed
- **FR-035**: System validates channel membership in real-time:
  - Checks if user is member of default channel
  - Handles private/restricted channel permissions
  - Caches membership status for performance
- **FR-036**: Admin can place orders on behalf of customers:
  - Admin selects customer from registered users
  - System sends private notification to customer about admin-placed order
  - Tracks order initiator (customer vs admin) in order record

### 2.3 Box Management
- **FR-009**: System automatically creates new boxes when:
  - Current box reaches capacity
  - Minimum breakeven quantity is met
- **FR-010**: System tracks box status:
  - Open (accepting orders)
  - Minimum reached (profitable)
  - Full (no more orders accepted)
  - Ordered (from wholesaler)
  - Delivered
- **FR-037**: System manages pre-order status transitions:
  - Automatically sets offers to "ordered" status when minimum quantity reached
  - Stores expected delivery date (free text field) when offer is ordered
  - Maintains status history with timestamps for audit trail
- **FR-038**: System sends vendor order confirmation to customers:
  - Notifies all customers when offer moves to "ordered" status
  - Includes expected delivery date if available
  - Distinguishes from initial order confirmation messages

### 2.4 Customer Management
- **FR-011**: Bot registers customer information:
  - Telegram user ID
  - Username
  - Order history
- **FR-012**: Customers can view their active orders
- **FR-013**: Customers can cancel orders (if box not yet ordered)
- **FR-046**: Admin can cancel any customer order with confirmation required for full boxes
- **FR-047**: System automatically corrects inventory when orders are cancelled
- **FR-048**: System notifies customers when their orders are cancelled by admin
- **FR-039**: System provides enhanced order tracking:
  - Shows pre-order status and disclaimers
  - Displays expected delivery dates when available
  - Tracks order status history for customer visibility
- **FR-040**: System manages admin-initiated orders:
  - Records order initiator (customer vs admin)
  - Sends private notifications for admin-placed orders
  - Maintains full audit trail of order source

### 2.5 Group Management
- **FR-014**: Admin can configure multiple groups:
  - Set default group for offers
  - Add exclusive/VIP groups
  - Configure group access levels
  - Manage group membership validation

- **FR-015**: System supports scheduled publishing:
  - Publish offer in primary group immediately
  - Auto-publish in secondary groups after specified hours
  - Track publishing status per group

### 2.6 Supplier Management
- **FR-017**: Admin can register suppliers with:
  - Supplier name
  - Contact information
  - Default wholesale terms
  - Status (active/inactive)

- **FR-018**: Admin can update supplier information
- **FR-019**: Admin can view supplier order history
- **FR-020**: System tracks orders per supplier for analytics

### 2.7 Discount Management
- **FR-021**: Admin can activate discount mode for all open offers:
  - Set discount percentage
  - Set expiry time in CE(S)T timezone
  - Apply to all currently open offers

- **FR-022**: System automatically sends notifications:
  - Discount start announcement to all groups with open offers
  - 10-minute warning before discount expires
  - Discount expiry notification to all affected groups

- **FR-023**: Discount pricing automatically applied to new orders during discount period

### 2.8 Delivery Management
- **FR-024**: Admin can mark offers as delivered
- **FR-025**: System processes delivery notifications:
  - Aggregates orders per customer for delivered offers
  - Sends private messages with order summary and total price
  - Includes payment link(s) in messages
  - Generates CSV pick list for admin

- **FR-026**: Delivery process handles batch processing:
  - Maximum 50 recipients per payment link
  - Multiple payment links for larger batches
  - Automatic batching and link assignment

### 2.9 Data Validation & Integrity
- **FR-027**: System validates all user inputs:
  - Sanitize text inputs to prevent injection attacks
  - Validate numeric inputs within acceptable ranges
  - Verify image file formats and sizes before upload
  - Check referential integrity before creating relationships

- **FR-028**: System maintains data consistency:
  - Validate offer-box relationships before order assignment
  - Check supplier status before creating offers
  - Verify group membership before publishing offers
  - Prevent orphaned records through cascade operations

- **FR-029**: System performs integrity checks:
  - Daily validation of order-box assignments
  - Cleanup of expired temporary data
  - Verification of image file accessibility
  - Detection and reporting of data inconsistencies

### 2.10 Audit Trail & Compliance
- **FR-030**: System logs all administrative actions:
  - Offer creation, modification, and deletion
  - Order cancellations and modifications
  - Supplier management operations
  - Group configuration changes
  - Discount activation and deactivation
  - Delivery status updates
  - Admin proxy orders and customer notifications

- **FR-031**: System tracks order modification history:
  - Original order details and timestamps
  - All modifications with user ID and timestamp
  - Cancellation reasons and timestamps
  - Status change audit trail
  - Order initiator tracking (customer vs admin)

- **FR-032**: System maintains data retention policies:
  - Archive completed orders after 2 years
  - Retain audit logs for 5 years
  - Automatic cleanup of temporary files
  - Configurable retention periods per data type

### 2.11 Channel Membership & Notifications
- **FR-041**: System validates and manages channel membership:
  - Real-time membership checks for default channel
  - Handles permission errors for private/restricted channels
  - Caches membership status for performance optimization
  - Provides fallback logic when membership cannot be determined

- **FR-042**: System manages notification templates:
  - Public order confirmation format with name/anonymous logic
  - Private admin-placed order notification template
  - Vendor order confirmation message format
  - Expected delivery date formatting and display

- **FR-043**: System handles notification delivery errors:
  - Retry logic for failed private messages
  - Fallback notifications for delivery failures
  - Error logging for notification system issues
  - Admin alerts for critical notification failures

### 2.12 Admin Order Management
- **FR-044**: Admin interface for proxy ordering:
  - Customer selection from registered users
  - Order placement workflow for admins
  - Bulk ordering capabilities for multiple customers
  - Order confirmation and tracking for admin-placed orders

- **FR-045**: System manages data model extensions:
  - Order initiator field (customer_id vs admin_id)
  - Expected delivery date storage and updates
  - Channel membership validation cache
  - Enhanced order status tracking with timestamps

### 2.13 Reporting & Analytics
- **FR-033**: Admin can view:
  - Current box status for all offers
  - Order summary per customer per group
  - Order summary per supplier
  - Profit calculations
  - Orders ready for wholesale purchase
  - Group-specific order statistics
  - Supplier performance analytics
  - Discount period performance metrics
  - Delivery status and pick lists
  - Data integrity reports and inconsistencies
  - Audit trail summaries and activity logs
  - Admin proxy order statistics and history
  - Channel membership validation reports

## 3. Technical Requirements

### 3.1 Platform
- **TR-001**: Telegram Bot API integration
- **TR-002**: Database for persistent storage (SQLite/PostgreSQL)
- **TR-003**: Python-based implementation

### 3.2 Data Storage
- **TR-004**: Store offers, orders, customers, boxes, and image data
- **TR-005**: Maintain order history and audit trail
- **TR-006**: Backup and recovery capabilities
- **TR-007**: Image storage and retrieval system
- **TR-008**: Support for common image formats (JPEG, PNG, WebP)

### 3.3 Performance
- **TR-009**: Handle concurrent orders
- **TR-010**: Response time < 2 seconds for order processing
- **TR-011**: Support up to 100 concurrent users
- **TR-012**: Efficient image handling and caching
- **TR-013**: Image compression for optimal Telegram delivery
- **TR-014**: Scheduled notification system for discount alerts
- **TR-015**: CE(S)T timezone support for discount timing

### 3.4 Data Validation
- **TR-016**: Input validation for all user data
- **TR-017**: SQL injection prevention
- **TR-018**: XSS protection for text inputs
- **TR-019**: File upload validation and sanitization
- **TR-020**: Referential integrity enforcement
- **TR-021**: Data consistency checks across operations

### 3.5 Audit & Compliance
- **TR-022**: Comprehensive audit logging system
- **TR-023**: Immutable audit trail storage
- **TR-024**: Configurable data retention policies
- **TR-025**: Automated data archival processes
- **TR-026**: Audit log query and reporting capabilities

## 4. User Stories

### 4.1 Admin Stories
- **US-001**: As an admin, I want to register suppliers so I can track orders per supplier
- **US-002**: As an admin, I want to create beer offers with images so customers can see the products
- **US-003**: As an admin, I want to add different images for each option (A, B, C) when available
- **US-004**: As an admin, I want to publish offers to specific groups for exclusive access
- **US-005**: As an admin, I want to schedule offers to auto-publish in other groups after a delay
- **US-006**: As an admin, I want to see which boxes are ready to order from wholesaler
- **US-007**: As an admin, I want to track profit margins per box
- **US-008**: As an admin, I want to manage customer orders and cancellations
- **US-009**: As an admin, I want to configure default and exclusive groups
- **US-010**: As an admin, I want to view order history per supplier
- **US-011**: As an admin, I want to activate discount mode for all open offers with automatic notifications
- **US-012**: As an admin, I want to mark offers as delivered and automatically notify customers with payment links
- **US-014**: As an admin, I want to place orders on behalf of customers so I can help members who have difficulty ordering or when customers have indicated they always want to buy a certain type of product (BIN/Buy It Now)
- **US-015**: As an admin, I want to set expected delivery dates when ordering from vendors so customers know when to expect their products
- **US-016**: As an admin, I want to see which orders were placed by me vs customers for proper tracking and accountability

### 4.2 Customer Stories
- **US-013**: As a customer, I want to see images of beer offers so I can make informed decisions
- **US-017**: As a customer, I want to receive order confirmation in the group so I can verify my order was placed
- **US-018**: As a customer, I want my name to show in confirmations only if I'm a group member for privacy
- **US-019**: As a customer, I want to be notified privately when an admin places an order for me
- **US-020**: As a customer, I want to know when my pre-order is actually ordered from the vendor
- **US-021**: As a customer, I want to see expected delivery dates when available so I can plan accordingly
- **US-022**: As a customer, I want to understand that all orders are pre-orders and not guaranteedf beer offers to make informed decisions
- **US-014**: As a customer, I want to see specific images for different options when available
- **US-015**: As a customer, I want to place orders for beer offers
- **US-016**: As a customer, I want to see which box my order is assigned to
- **US-017**: As a customer, I want to view my order status
- **US-018**: As a customer, I want to cancel my order if the box hasn't been ordered yet
- **US-019**: As a customer, I want to be notified about discount periods and receive discounted pricing
- **US-020**: As a customer, I want to receive delivery notifications with aggregated order summary and payment link

## 5. Bot Commands

### 5.1 Admin Commands
- `/add_supplier` - Register new supplier
- `/list_suppliers` - View all registered suppliers
- `/supplier_info <supplier_id>` - View supplier details and order history
- `/create_offer` - Create new beer offer with group targeting and image upload
- `/add_image <offer_id> [option]` - Add/update images for offers or specific options
- `/list_offers` - View all active offers
- `/close_offer <offer_id>` - Close an offer
- `/mark_delivered <offer_id>` - Mark offer as delivered
- `/delivery_process <payment_link1> [payment_link2] [...]` - Process delivery notifications for all delivered offers
- `/exclude_discount <offer_id>` - Exclude offer from all discount periods
- `/include_discount <offer_id>` - Include offer in discount periods
- `/discount_mode <percentage> <end_time_cest>` - Activate discount mode for all open offers
- `/end_discount` - Manually end active discount mode
- `/box_status` - View status of all boxes
- `/order_summary` - View orders ready for wholesale purchase
- `/supplier_orders <supplier_id>` - View orders for specific supplier
- `/customer_orders <user_id>` - View specific customer's orders
- `/configure_groups` - Set up default and exclusive groups
- `/schedule_publish <offer_id> <group_id> <hours>` - Schedule delayed publishing
- `/group_stats` - View order statistics per group
- `/audit_log [user_id] [action_type] [date_range]` - View audit trail
- `/data_integrity` - Run data consistency checks
- `/cleanup_data` - Remove expired temporary data
- `/cancel_order <order_id>` - Cancel customer order (requires confirmation for full boxes)

### 5.2 Customer Commands
- `/start` - Register as customer and view help
- `/offers` - View available offers
- `/order <offer_id> <option> <quantity>` - Place order
- `/my_orders` - View personal orders
- `/cancel_order <order_id>` - Cancel order
- `/info` - View project documentation links

### 5.3 Inline Commands
- Order placement via inline buttons on offer messages
- Quick status updates via callback queries

## 6. Data Models

### 6.1 Supplier
```
- supplier_id (Primary Key)
- name (String)
- contact_email (String, Optional)
- contact_phone (String, Optional)
- address (Text, Optional)
- default_terms (Text, Optional)
- status (Enum: active, inactive)
- created_at (DateTime)
- updated_at (DateTime)
```

### 6.2 Offer
```
- offer_id (Primary Key)
- supplier_name (String)
- name (String)
- description (Text)
- price_per_unit (Decimal)
- wholesale_box_size (Integer)
- min_quantity_breakeven (Integer)
- max_quantity (Integer, Optional)
- main_image_url (String, Optional) // Main offer image
- options (JSON) // For A, B, C variants with optional image URLs
- exclude_from_discounts (Boolean, Default: false)
- status (Enum: active, inactive, completed, delivered)
- created_at (DateTime)
- updated_at (DateTime)
```

### 6.3 Offer_Image
```
- image_id (Primary Key)
- offer_id (Foreign Key)
- option (String, Nullable) // null for main image, A/B/C for option images
- image_url (String)
- image_type (Enum: main, option)
- file_size (Integer)
- mime_type (String)
- created_at (DateTime)
```

### 6.4 Group
```
- group_id (Primary Key)
- telegram_group_id (Integer, Unique)
- group_name (String)
- group_type (Enum: default, exclusive, vip)
- is_default (Boolean)
- created_at (DateTime)
```

### 6.5 Offer_Group
```
- offer_group_id (Primary Key)
- offer_id (Foreign Key)
- group_id (Foreign Key)
- publish_delay_hours (Integer) // 0 for immediate
- published_at (DateTime, Nullable)
- message_id (Integer, Nullable) // Telegram message ID
- status (Enum: scheduled, published, failed)
```

### 6.6 Box
```
- box_id (Primary Key)
- offer_id (Foreign Key)
- option (String) // A, B, C, or null
- current_quantity (Integer)
- max_capacity (Integer)
- min_breakeven (Integer)
- status (Enum: open, minimum_reached, full, ordered, delivered)
- created_at (DateTime)
```

### 6.7 Order
```
- order_id (Primary Key)
- customer_id (Foreign Key)
- box_id (Foreign Key)
- offer_id (Foreign Key)
- group_id (Foreign Key) // Track which group order came from
- option (String)
- quantity (Integer)
- unit_price (Decimal)
- discount_percentage (Decimal, Default: 0) // Discount applied at order time
- total_price (Decimal)
- status (Enum: pending, confirmed, cancelled, delivered)
- created_at (DateTime)
```

### 6.8 Customer
```
- customer_id (Primary Key)
- telegram_user_id (Integer, Unique)
- username (String)
- first_name (String)
- last_name (String)
- created_at (DateTime)
```

### 6.9 Discount_Period
```
- discount_id (Primary Key)
- discount_percentage (Decimal)
- start_time (DateTime)
- end_time (DateTime)
- timezone (String) // CE(S)T
- status (Enum: active, expired, cancelled)
- created_at (DateTime)
```

### 6.10 Delivery_Batch
```
- batch_id (Primary Key)
- payment_link (String)
- batch_number (Integer)
- total_customers (Integer)
- total_amount (Decimal)
- processed_at (DateTime)
- created_at (DateTime)
```

### 6.11 Audit_Log
```
- audit_id (Primary Key)
- user_id (Foreign Key)
- action_type (Enum: create_offer, update_offer, delete_offer, create_order, cancel_order, update_supplier, etc.)
- entity_type (Enum: offer, order, supplier, customer, group)
- entity_id (String)
- old_values (JSON, Nullable)
- new_values (JSON, Nullable)
- timestamp (DateTime)
- ip_address (String, Optional)
- user_agent (String, Optional)
```

### 6.12 Data_Integrity_Check
```
- check_id (Primary Key)
- check_type (Enum: orphaned_orders, missing_images, invalid_references)
- status (Enum: pending, completed, failed)
- issues_found (Integer)
- details (JSON)
- executed_at (DateTime)
- completed_at (DateTime, Nullable)
```

## 7. Business Rules

### 7.1 Order Validation
- **BR-001**: Orders cannot exceed remaining box capacity
- **BR-002**: Orders cannot be placed on inactive offers
- **BR-003**: Customers can place multiple orders for same offer/option with confirmation
- **BR-046**: Orders can only be cancelled by customers if box status is "open" or "minimum_reached"
- **BR-047**: Admin can cancel any order regardless of box status with confirmation required for full boxes
- **BR-048**: Cancelled orders automatically reduce box quantity and recalculate box status
- **BR-049**: Customer notification required for all admin-cancelled orders
- **BR-005**: Offers must reference valid registered supplier name to be created
- **BR-006**: Wholesale box size must be one of: 1, 2, 6, 8, 10, 12, 15, 16, 18, 20, 24
- **BR-007**: Supplier names must be unique (case-insensitive)

### 7.2 Box Management
- **BR-007**: New box created when current box reaches capacity
- **BR-008**: Box marked as "minimum_reached" when breakeven quantity met
- **BR-009**: Box marked as "full" when max capacity reached
- **BR-010**: Admin must manually mark box as "ordered" after wholesale purchase

### 7.3 Group Management
- **BR-011**: Only one default group allowed per bot instance
- **BR-012**: Offers published to default group if no specific group selected
- **BR-013**: Scheduled publishing executes automatically based on delay hours
- **BR-014**: Orders tracked per group for analytics
- **BR-015**: Bot must be admin in target groups to post offers

### 7.4 Image Management
- **BR-016**: Main image displayed for all offer types
- **BR-017**: Option images override main image when available
- **BR-018**: Images must be under 20MB for Telegram compatibility
- **BR-019**: Supported formats: JPEG, PNG, WebP
- **BR-020**: Images automatically compressed if needed

### 7.5 Profit Calculation
- **BR-021**: Profit = (Customer_Price - Wholesale_Cost) * Quantity
- **BR-022**: Breakeven = Wholesale_Box_Cost / (Customer_Price - Unit_Wholesale_Cost)

### 7.6 Discount Management
- **BR-023**: Discount mode applies to all open offers except those excluded from discounts
- **BR-024**: Discount pricing calculated as: Original_Price * (1 - Discount_Percentage/100)
- **BR-025**: Only one active discount period allowed at a time
- **BR-026**: Discount notifications sent to all groups with published offers
- **BR-027**: 10-minute warning notification scheduled automatically
- **BR-028**: All times handled in CE(S)T timezone
- **BR-029**: Profit calculations always use original prices, not discounted prices
- **BR-030**: Offers with exclude_from_discounts=true maintain original pricing during discount periods
- **BR-031**: Discount percentage applied to order must be recorded in order record for reporting and customer messaging

### 7.7 Delivery Management
- **BR-032**: Offers can be marked as delivered only after being completed
- **BR-033**: Delivery process aggregates orders per customer for delivered offers
- **BR-034**: Maximum 50 customers per payment link batch
- **BR-035**: Payment links assigned sequentially to batches
- **BR-036**: CSV pick list includes: Customer Name, Product, Option, Quantity, Unit Price, Discount %, Total Price
- **BR-037**: Private messages sent only to customers with delivered orders
- **BR-038**: Order aggregation combines same products with quantities and totals

### 7.8 Data Validation & Integrity
- **BR-039**: All user inputs must be validated and sanitized before processing
- **BR-040**: Numeric inputs must be within defined ranges (quantities > 0, prices > 0)
- **BR-041**: Text inputs limited to maximum lengths and safe characters only
- **BR-042**: Image uploads restricted to admin user only (ID: 15005473)
- **BR-043**: Referential integrity enforced before creating relationships
- **BR-044**: Daily automated checks for orphaned records and data inconsistencies
- **BR-045**: System prevents creation of orders for inactive offers or suppliers
- **BR-046**: Cascade deletions maintain data consistency across related entities

### 7.9 Audit Trail & Compliance
- **BR-047**: All administrative actions must be logged with timestamp and user ID
- **BR-048**: Order modifications tracked with complete before/after state
- **BR-049**: Audit logs are immutable and cannot be deleted by users
- **BR-050**: Data retention: orders archived after 2 years, audit logs kept for 5 years
- **BR-051**: Automated cleanup of temporary data older than 24 hours
- **BR-052**: System maintains complete chain of custody for all order state changes
- **BR-053**: Audit trail includes IP address and user agent when available

## 8. Security Requirements

### 8.1 Access Control
- **SR-001**: Admin commands restricted to Telegram user ID 15005473 (siebrand)
- **SR-002**: Customer data privacy protection
- **SR-003**: Order modification restricted to order owner

### 8.2 Data Protection
- **SR-004**: Secure storage of customer information
- **SR-005**: Input validation for all user inputs
- **SR-006**: Rate limiting to prevent spam
- **SR-007**: Secure image storage with access controls
- **SR-008**: Image content validation to prevent malicious uploads
- **SR-009**: SQL injection prevention through parameterized queries
- **SR-010**: XSS protection for all text inputs
- **SR-011**: File upload restricted to admin user only
- **SR-012**: Audit log integrity protection
- **SR-013**: Immutable audit trail storage

## 9. Technical Requirements

### 9.1 Environment Management
- **TR-001**: Two environments required: test and production
- **TR-002**: All deployments must be staged to test environment first
- **TR-003**: Production deployments require human approval after test validation
- **TR-004**: Environment-specific configuration management
- **TR-005**: All messages in test environment must be prefixed with "TEST - "

### 9.2 Documentation Publishing
- **TR-006**: Requirements document must be publicly accessible via CloudFront
- **TR-007**: AWS architecture document must be publicly accessible via CloudFront
- **TR-008**: Bot must provide /info command with URLs to public documentation

## 10. Error Handling

### 10.1 User Errors
- **EH-001**: Clear error messages for invalid orders
- **EH-002**: Graceful handling of cancelled/completed offers
- **EH-003**: Validation feedback for incorrect command usage

### 10.2 System Errors
- **EH-004**: Database connection error handling
- **EH-005**: Telegram API error recovery
- **EH-006**: Logging for debugging and monitoring
- **EH-007**: Image upload failure handling
- **EH-008**: Image format validation errors
- **EH-009**: Graceful degradation when images unavailable
- **EH-010**: Data validation error reporting
- **EH-011**: Audit log write failure handling
- **EH-012**: Data integrity check failure recovery
- **EH-013**: Referential integrity violation handling

## 11. Future Enhancements

### 11.1 Phase 2 Features
- Payment integration
- Delivery tracking
- Customer notifications
- Automated wholesale ordering
- Multi-language support
- Web dashboard for admin
- Advanced group management (member verification)
- Cross-group order limits
- Group-specific pricing
- Recurring discount schedules
- Customer-specific discounts

### 11.2 Integration Possibilities
- Inventory management systems
- Accounting software
- Customer relationship management (CRM)
- Analytics and reporting tools

## 12. Success Criteria

- **SC-001**: Bot successfully processes 99.99% of valid orders
- **SC-002**: Admin can track box status in real-time
- **SC-003**: Customers receive immediate order confirmation
- **SC-004**: Zero data loss during order processing
- **SC-005**: System handles peak load during offer announcements
