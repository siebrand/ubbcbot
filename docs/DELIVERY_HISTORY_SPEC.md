# Delivery History Specification

## Overview
This specification defines how users can query and export complete delivery history using the existing `OrderHistory` table infrastructure. The system logs `PAYMENT_RECEIVED` events when orders reach `completed` status, containing all necessary information: customer name, offer name, amount, timestamp, and order ID.

## Current State Analysis

### Existing Infrastructure
- **OrderHistory Table**: Already deployed with GSI indexes for efficient querying
- **Audit Service**: Automatically logs all order events (creation, cancellation, status changes, payments)
- **TTL**: 5 years (prod), 90 days (test)
- **Export System**: CSV export functionality exists for orders

### Available Data Points
The `PAYMENT_RECEIVED` event type contains:
- `customer_name` - Denormalized customer name (persists even if customer deleted)
- `offer_name` - Denormalized offer name (persists even if offer deleted)
- `amount` - Order total price (Decimal)
- `changed_at` - Completion timestamp (datetime)
- `order_id` - Full order ID
- `changed_by` - Admin user ID who marked as paid
- All data available in single event, no joins required

### Existing GSI Indexes (Query Efficient)
1. **order-index**: `order_id` (HASH) + `changed_at` (RANGE) - Get full history for specific order
2. **customer-event-index**: `customer_event` (HASH) + `changed_at` (RANGE) - Get events by customer and type
3. **event-date-index**: `event_date` (HASH) - Get all events of specific type in date range
4. **customer-name-event-index**: `customer_name_event` (HASH) + `changed_at` (RANGE) - Query by customer name (for deleted customers)

## Proposed Commands

### Admin Commands

#### 1. `/delivery_history [customer_name|username] [days]`
**Purpose**: View completed delivery history (status=completed) for specific customer or all customers

**Usage**:
```
/delivery_history                    # All customers, last 30 days
/delivery_history John               # Specific customer, last 30 days
/delivery_history @johndoe 90        # Specific user, last 90 days
/delivery_history all 7              # All customers, last 7 days
```

**Query Strategy**:
- Single customer: Use `customer-event-index` with `customer_id#PAYMENT_RECEIVED`
- All customers: Use `event-date-index` with `PAYMENT_RECEIVED` event type + date range
- Filter by date range (changed_at >= cutoff)

**Output Format** (Single line per delivery):
```
📦 Delivery History - John Doe (Last 30 days)

2024-01-15 | Brouwerij West IPA | 6x | €45.00
2024-01-20 | De Molen Stout | 12x | €90.00
2024-01-25 | Oedipus IPA | 6x | €42.00

Total: 3 deliveries | 24 units | €177.00
```

**Message Splitting**:
- Telegram limit: 4096 UTF-8 characters
- Split at line breaks when approaching limit
- Each message includes header with continuation indicator
- Example for long lists:
  ```
  📦 Delivery History - All Customers (Last 30 days) [1/3]
  
  [lines...]
  
  📦 Delivery History - All Customers (Last 30 days) [2/3]
  
  [lines...]
  
  📦 Delivery History - All Customers (Last 30 days) [3/3]
  
  [lines...]
  Total: 150 deliveries | 1200 units | €9,450.00
  ```

#### 2. `/export_delivery_history [customer_name|all] [days] [format]`
**Purpose**: Export delivery history as CSV

**Usage**:
```
/export_delivery_history                    # All customers, 30 days, standard
/export_delivery_history John 90            # Specific customer, 90 days
/export_delivery_history all 365 full       # All customers, 1 year, full details
```

**Query Strategy**: Same as `/delivery_history` but generates CSV export

**CSV Formats**:

**Standard Format**:
```csv
Date,Customer,Offer,Quantity,Amount
2024-01-15,John Doe,Brouwerij West IPA,6,45.00
2024-01-20,John Doe,De Molen Stout,12,90.00
```

**Full Format** (All fields):
```csv
history_id,order_id,customer_id,customer_name,offer_name,event_type,changed_at,changed_by,amount
abc-123,order-456,cust-789,John Doe,Brouwerij West IPA,PAYMENT_RECEIVED,2024-01-15T10:30:00Z,123456,45.00
```

#### 3. `/payment_history [customer_name|all] [days]`
**Purpose**: Alias for `/delivery_history` (same data, different command name)

**Note**: Since completed status = payment received, this is functionally identical to `/delivery_history`

#### 4. `/order_audit <order_id>`
**Purpose**: View complete audit trail for specific order

**Usage**:
```
/order_audit abc123de
```

**Query Strategy**:
- Use `order-index` GSI: Direct query on `order_id`
- Most efficient query (single partition key lookup)

**Output Format**:
```
📋 Order Audit Trail - abc123de

Customer: John Doe | Offer: Brouwerij West IPA | Quantity: 6 units

2024-01-10 | ORDER_CREATED | customer | Total: €45.00
2024-01-12 | STATUS_CHANGED | ordered → ready_for_labeling | @admin_user
2024-01-15 | STATUS_CHANGED | ready_for_labeling → labeling_completed | @admin_user
2024-01-20 | PAYMENT_RECEIVED | €45.00 | @admin_user
```

**Message Splitting**: Apply same 4096 character limit with line-break splitting

### Customer Commands

#### 5. `/my_delivery_history`
**Purpose**: View personal delivery history

**Usage**:
```
/my_delivery_history
```

**Query Strategy**:
- Use `customer-event-index` with authenticated user's `customer_id`
- Filter for delivery-related events only

**Output Format**:
```
📦 My Delivery History

2024-01-15 | Brouwerij West IPA | 6x | €45.00
2024-01-20 | De Molen Stout | 12x | €90.00

Total: 2 deliveries | 18 units | €135.00
```

**Message Splitting**: Apply same 4096 character limit with line-break splitting

## Implementation Plan

### Phase 1: Core Query Functions (Database Layer)
**File**: `src/services/database.py`

Add methods:
```python
def get_completed_deliveries(self, customer_id: Optional[str] = None, days: int = 30) -> List[OrderHistory]:
    """Get PAYMENT_RECEIVED events (completed deliveries)"""
    # Use customer-event-index or event-date-index
    # Filter: event_type = 'PAYMENT_RECEIVED', changed_at >= cutoff
```

**Complexity**: Low (leverage existing GSI queries)

### Phase 2: Message Splitting Utility
**File**: `src/utils/message_splitter.py` (new)

Implement:
```python
def split_message(text: str, max_length: int = 4096) -> List[str]:
    """Split message at line breaks, respecting UTF-8 encoding"""
    # Split at \n closest to but not exceeding max_length bytes
    # Return list of message chunks
```

**Complexity**: Low

### Phase 3: Admin Commands
**File**: `src/handlers/admin/delivery_history_commands.py` (new)

Implement:
- `/delivery_history` - View completed deliveries (single line format)
- `/export_delivery_history` - Export as CSV
- `/payment_history` - Alias for `/delivery_history`
- `/order_audit` - View order audit trail (single line format)

**Complexity**: Medium (message splitting, CSV export)

### Phase 4: Customer Commands
**File**: `src/handlers/customer/order_commands.py`

Add:
- `/my_delivery_history` - Personal delivery history

### Phase 4: Customer Commands
**File**: `src/handlers/customer/order_commands.py`

Add:
- `/my_delivery_history` - Personal delivery history (single line format)

**Complexity**: Low

### Phase 5: Command Router Integration
**File**: `src/services/command_router.py`

Register new commands with proper routing

### Phase 5: Command Router Integration
**File**: `src/services/command_router.py`

Register new commands with proper routing

**Complexity**: Low

### Phase 6: Translations
**Files**: `src/translations/en.json`, `src/translations/nl.json`

Add translation keys for all new messages

### Phase 6: Translations
**Files**: `src/translations/en.json`, `src/translations/nl.json`

Add translation keys for all new messages

**Complexity**: Low

### Phase 7: Admin Panel Integration
### Phase 7: Admin Panel Integration
**File**: `src/handlers/admin/admin_commands.py`

Add buttons to admin panel for quick access

**Complexity**: Low

## Query Performance Analysis

### Most Efficient Queries (Single Partition)
1. **Order Audit** (`/order_audit`): Direct lookup on `order-index`
   - Query: `order_id = 'abc123'`
   - Performance: O(1) - Single partition read

2. **Customer Delivery History** (`/delivery_history John`): Query on `customer-event-index`
   - Query: `customer_event = 'customer_id#PAYMENT_RECEIVED' AND changed_at >= cutoff`
   - Performance: O(log n) - Single partition with range query

### Moderate Efficiency (Event Type Partition)
3. **All Customers Delivery History** (`/delivery_history all`): Query on `event-date-index`
   - Query: `event_date BETWEEN 'PAYMENT_RECEIVED#2024-01-01' AND 'PAYMENT_RECEIVED#2024-01-31'`
   - Performance: O(n) - Scans PAYMENT_RECEIVED partition for date range
   - Optimization: Limit date range to reduce scan size (default 30 days)

## Message Splitting Implementation

### UTF-8 Character Limit
- Telegram limit: 4096 bytes (UTF-8 encoded)
- Split strategy: Find last `\n` before byte limit
- Continuation headers: `[1/3]`, `[2/3]`, `[3/3]`
- Total summary: Only in final message

### Example Split Logic
```python
def split_message(text: str, max_bytes: int = 4000) -> List[str]:
    """Split at line breaks, staying under byte limit"""
    # Leave 96 bytes buffer for continuation header
    # Find last \n before max_bytes
    # Add [X/Y] to each chunk header
```

## Data Retention & TTL

- **Production**: 5 years (1825 days)
- **Test**: 90 days
- **Automatic Cleanup**: DynamoDB TTL handles expiration
- **Manual Cleanup**: Not needed (TTL managed)

## Export File Naming Convention

```
delivery_history_{environment}_{customer|all}_{YYYYMMDD_HHMMSS}.csv
payment_history_{environment}_{customer|all}_{YYYYMMDD_HHMMSS}.csv
order_audit_{order_id}_{YYYYMMDD_HHMMSS}.csv
```

Examples:
- `delivery_history_prod_john_doe_20240115_143000.csv`
- `payment_history_test_all_20240115_143000.csv`
- `order_audit_abc123de_20240115_143000.csv`

## Translation Keys Required

### English (en.json)
```json
{
  "commands.delivery_history.description": "View completed delivery history",
  "commands.export_delivery_history.description": "Export delivery history as CSV",
  "commands.payment_history.description": "View payment history (alias for delivery_history)",
  "commands.order_audit.description": "View complete order audit trail",
  "commands.my_delivery_history.description": "View my delivery history",
  
  "delivery_history.header": "📦 Delivery History - {customer_name} (Last {days} days)",
  "delivery_history.all_header": "📦 Delivery History - All Customers (Last {days} days)",
  "delivery_history.continuation": "📦 Delivery History - {customer_name} (Last {days} days) [{page}/{total_pages}]",
  "delivery_history.no_history": "No completed deliveries found for the specified period.",
  "delivery_history.total": "Total: {count} deliveries | {units} units | €{amount}",
  
  "order_audit.header": "📋 Order Audit Trail - {order_id}",
  "order_audit.summary": "Customer: {customer_name} | Offer: {offer_name} | Quantity: {quantity} units",
  
  "export.delivery_history_caption": "Delivery history export ({customer_name}, {count} records)"
}
```

### Dutch (nl.json)
```json
{
  "commands.delivery_history.description": "Bekijk voltooide leveringsgeschiedenis",
  "commands.export_delivery_history.description": "Exporteer leveringsgeschiedenis als CSV",
  "commands.payment_history.description": "Bekijk betalingsgeschiedenis (alias voor delivery_history)",
  "commands.order_audit.description": "Bekijk volledige bestelaudit",
  "commands.my_delivery_history.description": "Bekijk mijn leveringsgeschiedenis",
  
  "delivery_history.header": "📦 Leveringsgeschiedenis - {customer_name} (Laatste {days} dagen)",
  "delivery_history.all_header": "📦 Leveringsgeschiedenis - Alle Klanten (Laatste {days} dagen)",
  "delivery_history.continuation": "📦 Leveringsgeschiedenis - {customer_name} (Laatste {days} dagen) [{page}/{total_pages}]",
  "delivery_history.no_history": "Geen voltooide leveringen gevonden voor de opgegeven periode.",
  "delivery_history.total": "Totaal: {count} leveringen | {units} stuks | €{amount}",
  
  "order_audit.header": "📋 Bestelaudit - {order_id}",
  "order_audit.summary": "Klant: {customer_name} | Aanbieding: {offer_name} | Aantal: {quantity} stuks",
  
  "export.delivery_history_caption": "Leveringsgeschiedenis export ({customer_name}, {count} records)"
}
```

## Security & Access Control

### Admin Commands
- `/delivery_history` - Admin only
- `/export_delivery_history` - Admin only
- `/payment_history` - Admin only
- `/order_audit` - Admin only

### Customer Commands
- `/my_delivery_history` - Authenticated customers only (approved status)
- Customers can only view their own history

## Testing Checklist

### Unit Tests
- [ ] Database query methods return correct results
- [ ] Date range filtering works correctly
- [ ] Customer filtering works correctly
- [ ] CSV generation produces valid format

### Integration Tests
- [ ] Commands work in private chat
- [ ] Commands work in group chat (admin only)
- [ ] Pagination works correctly
- [ ] Export generates downloadable files
- [ ] Translations display correctly (EN/NL)

### Performance Tests
- [ ] Single order audit completes < 1s
- [ ] Customer history (30 days) completes < 2s
- [ ] All customers history (30 days) completes < 5s
- [ ] CSV export (1000 records) completes < 10s

## Future Enhancements (Out of Scope)

1. **Graphical Reports**: Charts showing delivery trends over time
2. **Email Notifications**: Automatic delivery history emails to customers
3. **Advanced Filters**: Filter by offer, supplier, status, date range
4. **Scheduled Exports**: Automatic weekly/monthly exports
5. **API Endpoints**: REST API for external integrations
6. **Real-time Webhooks**: Push notifications for delivery events

## Estimated Implementation Time

- Phase 1 (Database): 1 hour
- Phase 2 (Message Splitter): 1 hour
- Phase 3 (Admin Commands): 3 hours
- Phase 4 (Customer Commands): 1 hour
- Phase 5 (Router Integration): 1 hour
- Phase 6 (Translations): 1 hour
- Phase 7 (Admin Panel): 1 hour
- Testing & Documentation: 2 hours

**Total**: ~11 hours

## Success Criteria

- [ ] Admins can view completed delivery history for any customer (single line format)
- [ ] Admins can export delivery history as CSV
- [ ] Admins can view complete order audit trail
- [ ] Customers can view their own delivery history
- [ ] All queries use PAYMENT_RECEIVED event type exclusively
- [ ] Messages split at line breaks when exceeding 4096 bytes
- [ ] Continuation headers show page numbers [X/Y]
- [ ] Total summary includes deliveries, units, and amount
- [ ] All queries complete within performance targets
- [ ] CSV exports are properly formatted and downloadable
- [ ] All commands have proper translations (EN/NL)
- [ ] Commands are integrated into admin panel
- [ ] Documentation is complete and accurate
