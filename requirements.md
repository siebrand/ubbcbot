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
  - Beer name/description
  - Price per unit
  - Wholesale box size (e.g., 12 units)
  - Minimum quantity needed for breakeven
  - Maximum quantity (optional)
  - Multiple options (A, B, C) if applicable
  - Target groups (default + additional groups)
  - Publishing schedule (immediate or delayed)
  - Offer status (active/inactive/completed)

- **FR-002**: Admin can post offers to specific Telegram groups
- **FR-003**: Admin can schedule offers to publish in additional groups after delay
- **FR-004**: Admin can update offer details
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

### 2.6 Reporting & Analytics
- **FR-016**: Admin can view:
  - Current box status for all offers
  - Order summary per customer per group
  - Profit calculations
  - Orders ready for wholesale purchase
  - Group-specific order statistics

## 3. Technical Requirements

### 3.1 Platform
- **TR-001**: Telegram Bot API integration
- **TR-002**: Database for persistent storage (SQLite/PostgreSQL)
- **TR-003**: Python-based implementation

### 3.2 Data Storage
- **TR-004**: Store offers, orders, customers, and boxes data
- **TR-005**: Maintain order history and audit trail
- **TR-006**: Backup and recovery capabilities

### 3.3 Performance
- **TR-007**: Handle concurrent orders
- **TR-008**: Response time < 2 seconds for order processing
- **TR-009**: Support up to 100 concurrent users

## 4. User Stories

### 4.1 Admin Stories
- **US-001**: As an admin, I want to create beer offers so customers can place orders
- **US-002**: As an admin, I want to publish offers to specific groups for exclusive access
- **US-003**: As an admin, I want to schedule offers to auto-publish in other groups after a delay
- **US-004**: As an admin, I want to see which boxes are ready to order from wholesaler
- **US-005**: As an admin, I want to track profit margins per box
- **US-006**: As an admin, I want to manage customer orders and cancellations
- **US-007**: As an admin, I want to configure default and exclusive groups

### 4.2 Customer Stories
- **US-005**: As a customer, I want to place orders for beer offers
- **US-006**: As a customer, I want to see which box my order is assigned to
- **US-007**: As a customer, I want to view my order status
- **US-008**: As a customer, I want to cancel my order if the box hasn't been ordered yet

## 5. Bot Commands

### 5.1 Admin Commands
- `/create_offer` - Create new beer offer with group targeting
- `/list_offers` - View all active offers
- `/close_offer <offer_id>` - Close an offer
- `/box_status` - View status of all boxes
- `/order_summary` - View orders ready for wholesale purchase
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

### 6.1 Offer
```
- offer_id (Primary Key)
- name (String)
- description (Text)
- price_per_unit (Decimal)
- wholesale_box_size (Integer)
- min_quantity_breakeven (Integer)
- max_quantity (Integer, Optional)
- options (JSON) // For A, B, C variants
- status (Enum: active, inactive, completed)
- created_at (DateTime)
- updated_at (DateTime)
```

### 6.2 Group
```
- group_id (Primary Key)
- telegram_group_id (Integer, Unique)
- group_name (String)
- group_type (Enum: default, exclusive, vip)
- is_default (Boolean)
- created_at (DateTime)
```

### 6.3 Offer_Group
```
- offer_group_id (Primary Key)
- offer_id (Foreign Key)
- group_id (Foreign Key)
- publish_delay_hours (Integer) // 0 for immediate
- published_at (DateTime, Nullable)
- message_id (Integer, Nullable) // Telegram message ID
- status (Enum: scheduled, published, failed)
```

### 6.4 Box
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

### 6.5 Order
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

### 6.6 Customer
```
- customer_id (Primary Key)
- telegram_user_id (Integer, Unique)
- username (String)
- first_name (String)
- last_name (String)
- created_at (DateTime)
```

## 7. Business Rules

### 7.1 Order Validation
- **BR-001**: Orders cannot exceed remaining box capacity
- **BR-002**: Orders cannot be placed on inactive offers
- **BR-003**: Customers cannot place duplicate orders for same offer/option
- **BR-004**: Orders can only be cancelled if box status is "open" or "minimum_reached"

### 7.2 Box Management
- **BR-005**: New box created when current box reaches capacity
- **BR-006**: Box marked as "minimum_reached" when breakeven quantity met
- **BR-007**: Box marked as "full" when max capacity reached
- **BR-008**: Admin must manually mark box as "ordered" after wholesale purchase

### 7.3 Group Management
- **BR-009**: Only one default group allowed per bot instance
- **BR-010**: Offers published to default group if no specific group selected
- **BR-011**: Scheduled publishing executes automatically based on delay hours
- **BR-012**: Orders tracked per group for analytics
- **BR-013**: Bot must be admin in target groups to post offers

### 7.4 Profit Calculation
- **BR-014**: Profit = (Customer_Price - Wholesale_Cost) * Quantity
- **BR-015**: Breakeven = Wholesale_Box_Cost / (Customer_Price - Unit_Wholesale_Cost)

## 8. Security Requirements

### 8.1 Access Control
- **SR-001**: Admin commands restricted to authorized users
- **SR-002**: Customer data privacy protection
- **SR-003**: Order modification restricted to order owner

### 8.2 Data Protection
- **SR-004**: Secure storage of customer information
- **SR-005**: Input validation for all user inputs
- **SR-006**: Rate limiting to prevent spam

## 9. Error Handling

### 9.1 User Errors
- **EH-001**: Clear error messages for invalid orders
- **EH-002**: Graceful handling of cancelled/completed offers
- **EH-003**: Validation feedback for incorrect command usage

### 9.2 System Errors
- **EH-004**: Database connection error handling
- **EH-005**: Telegram API error recovery
- **EH-006**: Logging for debugging and monitoring

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