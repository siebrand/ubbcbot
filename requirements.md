# Telegram Beer Ordering Bot - Requirements Document

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
  - Supplier (from registered suppliers)
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

### 2.4 Customer Management
- **FR-011**: Bot registers customer information:
  - Telegram user ID
  - Username
  - Order history
- **FR-012**: Customers can view their active orders
- **FR-013**: Customers can cancel orders (if box not yet ordered)

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

### 2.9 Reporting & Analytics
- **FR-027**: Admin can view:
  - Current box status for all offers
  - Order summary per customer per group
  - Order summary per supplier
  - Profit calculations
  - Orders ready for wholesale purchase
  - Group-specific order statistics
  - Supplier performance analytics
  - Discount period performance metrics
  - Delivery status and pick lists

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

### 4.2 Customer Stories
- **US-013**: As a customer, I want to see images of beer offers to make informed decisions
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

### 5.2 Customer Commands
- `/start` - Register as customer and view help
- `/offers` - View available offers
- `/order <offer_id> <option> <quantity>` - Place order
- `/my_orders` - View personal orders
- `/cancel_order <order_id>` - Cancel order

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
- supplier_id (Foreign Key)
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

## 7. Business Rules

### 7.1 Order Validation
- **BR-001**: Orders cannot exceed remaining box capacity
- **BR-002**: Orders cannot be placed on inactive offers
- **BR-003**: Customers cannot place duplicate orders for same offer/option
- **BR-004**: Orders can only be cancelled if box status is "open" or "minimum_reached"
- **BR-005**: Offers must have valid active supplier to be created
- **BR-006**: Wholesale box size must be one of: 1, 2, 6, 8, 10, 12, 15, 16, 18, 20, 24

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

### 7.7 Delivery Management
- **BR-031**: Offers can be marked as delivered only after being completed
- **BR-032**: Delivery process aggregates orders per customer for delivered offers
- **BR-033**: Maximum 50 customers per payment link batch
- **BR-034**: Payment links assigned sequentially to batches
- **BR-035**: CSV pick list includes: Customer Name, Product, Option, Quantity, Unit Price, Total Price
- **BR-036**: Private messages sent only to customers with delivered orders
- **BR-037**: Order aggregation combines same products with quantities and totals

## 8. Security Requirements

### 8.1 Access Control
- **SR-001**: Admin commands restricted to authorized users
- **SR-002**: Customer data privacy protection
- **SR-003**: Order modification restricted to order owner

### 8.2 Data Protection
- **SR-004**: Secure storage of customer information
- **SR-005**: Input validation for all user inputs
- **SR-006**: Rate limiting to prevent spam
- **SR-007**: Secure image storage with access controls
- **SR-008**: Image content validation to prevent malicious uploads

## 9. Error Handling

### 9.1 User Errors
- **EH-001**: Clear error messages for invalid orders
- **EH-002**: Graceful handling of cancelled/completed offers
- **EH-003**: Validation feedback for incorrect command usage

### 9.2 System Errors
- **EH-004**: Database connection error handling
- **EH-005**: Telegram API error recovery
- **EH-006**: Logging for debugging and monitoring
- **EH-007**: Image upload failure handling
- **EH-008**: Image format validation errors
- **EH-009**: Graceful degradation when images unavailableg for debugging and monitoring

## 10. Future Enhancements

### 10.1 Phase 2 Features
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

### 10.2 Integration Possibilities
- Inventory management systems
- Accounting software
- Customer relationship management (CRM)
- Analytics and reporting tools

## 11. Success Criteria

- **SC-001**: Bot successfully processes 95% of valid orders
- **SC-002**: Admin can track box status in real-time
- **SC-003**: Customers receive immediate order confirmation
- **SC-004**: Zero data loss during order processing
- **SC-005**: System handles peak load during offer announcements
