# Customer Credit System Specification

## Problem Statement

Customers may need credits for various reasons:
- Order cancelled by admin after payment
- Defective/incorrect product delivered
- Customer dissatisfaction
- Goodwill gestures
- Manual adjustments

**Key Challenge:** Credit amounts may exceed the customer's next delivery total, requiring a balance system.

## Business Requirements

### Core Functionality
1. Admin can issue credits to customers
2. Credits can be any amount and are not tied to orders
3. Credits create a credit balance for the customer
4. Credit balance is automatically applied to future deliveries
5. Credit balance can exceed next delivery amount (carry forward)
6. Admin can view customer credit balances
7. Admin can manually adjust credit balances
8. Customers can view their credit balance
9. Delivery overviews show credit balance and adjusted payment amount

### Credit Scenarios

**Scenario 1: Simple Credit (Credit < Next Delivery)**
- Customer has €20 credit
- Next delivery total: €50
- Payment required: €30

**Scenario 2: Large Credit (Credit > Next Delivery)**
- Customer has €60 credit
- Next delivery total: €50
- Payment required: €0
- Remaining credit: €10 (carries forward)

**Scenario 3: Multiple Deliveries with Credit**
- Customer has €100 credit
- Delivery 1: €40 → €0 payment, €60 credit remains
- Delivery 2: €35 → €0 payment, €25 credit remains
- Delivery 3: €30 → €0 payment, €0 credit remains (credit depleted)

**Scenario 4: Partial Credit**
- Admin issues €20 credit for defective items
- Customer credit: €20

## Data Model Changes

### New Table: Customer Credits

**DynamoDB Table:** `ubbc-bot-{environment}-customer-credits`

**Primary Key:** `customer_id` (String)

**Attributes:**
```python
@dataclass
class CustomerCredit:
    customer_id: str  # Primary key
    current_balance: Decimal = Decimal('0.0')  # Current credit balance
    total_credits_issued: Decimal = Decimal('0.0')  # Lifetime total credits
    total_credits_used: Decimal = Decimal('0.0')  # Lifetime total used
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### New Table: Credit Transactions

**DynamoDB Table:** `ubbc-bot-{environment}-credit-transactions`

**Primary Key:** `transaction_id` (String, UUID)
**GSI:** `customer-index` on `customer_id`

**Attributes:**
```python
@dataclass
class CreditTransaction:
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str = ""
    transaction_type: str = ""  # CREDIT_ISSUED, ADJUSTMENT, APPLIED, MANUAL_ADD, MANUAL_SUBTRACT
    amount: Decimal = Decimal('0.0')  # Positive for credits, negative for usage
    balance_before: Decimal = Decimal('0.0')
    balance_after: Decimal = Decimal('0.0')
    reason: str = ""  # Admin-provided reason
    created_by: int = 0  # Admin user ID
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### New Table: Order History (Audit Log)

**DynamoDB Table:** `ubbc-bot-{environment}-order-history`

**Primary Key:** `history_id` (String, UUID)
**GSI:** `order-index` on `order_id`

**Purpose:** Track all changes to orders for audit trail and compliance.

**Attributes:**
```python
@dataclass
class OrderHistory:
    history_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str = ""  # Links to Order
    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    changed_by: int = 0  # Admin user ID (0 for system changes)
    field_name: str = ""  # Field that changed (e.g., "unit_price", "status", "quantity")
    old_value: str = ""  # Previous value (as string)
    new_value: str = ""  # New value (as string)
    reason: str = ""  # Admin-provided reason for change
    
    # TTL for automatic cleanup (2 years)
    ttl: Optional[int] = None  # Unix timestamp for DynamoDB TTL
```

### Modified Entities

**Customer** - No changes needed (credit is separate table)

**Order** - No changes needed (credits are independent of orders)

## Transaction Types

| Type | Description | Amount Sign | Example |
|------|-------------|-------------|---------|
| CREDIT_ISSUED | Credit issued to customer | Positive | +€20.00 |
| ADJUSTMENT | Admin manual adjustment | Positive/Negative | +€5.00 or -€5.00 |
| APPLIED | Credit applied to delivery | Negative | -€30.00 |
| MANUAL_ADD | Admin adds credit | Positive | +€10.00 |
| MANUAL_SUBTRACT | Admin removes credit | Negative | -€10.00 |


## Audit Trail Integration

### Purpose

The Order History table provides a complete audit trail:
- **Credit Transactions** track money movements (credits issued, credits applied)
- **Order History** tracks data changes (what changed, why, and who changed it)

Together they answer:
- "What changed?" → Order History shows data modifications
- "What credit was issued?" → Credit Transaction shows credit amount
- "Who made the change?" → Both tables track admin_id
- "When did it happen?" → Both tables have timestamps

### Audit Trail Flow

**Example: Admin Issues Credit for Defective Product**

1. **Admin issues credit** (independent of order)
   ```python
   # Credit Transaction created
   CreditTransaction(
       transaction_id="txn-001",
       customer_id="cust-123",
       transaction_type="CREDIT_ISSUED",
       amount=20.00,
       reason="2 bottles defective",
       created_by=<ADMIN_USER_ID>
   )
   ```

2. **Complete audit trail established**
   - Credit Transaction: Shows credit issued (€20)
   - No order linkage required

### Query Capabilities

**Query 1: "Show all credits issued"**
```python
# Get credit transactions
credits = get_credit_transactions(type="CREDIT_ISSUED")

# Results:
# - €20.00 issued to John Doe - "2 bottles defective"
# - €15.00 issued to Jane Smith - "Goodwill gesture"
```

**Query 2: "Show all actions by admin"**
```python
# Get order changes by admin
order_changes = get_order_history_by_admin(admin_id)

# Get credit transactions by admin
credit_actions = get_credit_transactions_by_admin(admin_id)

# Combined view of all admin actions
```

### Data Retention

**Order History:**
- TTL: 5 years production, 90 days test (automatic DynamoDB cleanup)
- Rationale: 5-year retention for financial/tax compliance in prod, short retention in test
- Cost: ~$0.08/month production (assuming 1000 records/year)

**Credit Transactions:**
- No TTL (permanent record)
- Rationale: Financial records should be permanent
- Cost: ~$0.02/month

### Implementation Notes

**Audit Enforcement:**
- All order modifications automatically log to audit trail (database-level enforcement)
- Use transaction methods for sensitive operations: `cancel_order_with_audit()`, `adjust_order_price_with_audit()`, `mark_order_paid_with_audit()`
- See `docs/audit-enforcement.md` for complete enforcement strategy

**When to log Order History:**
- Price changes (unit_price, total_price)
- Quantity changes
- Status changes (if significant)

**When NOT to log:**
- Automatic system updates (update_date)
- Non-significant status transitions
- Read operations

**Logging helper:**
```python
def log_order_change(order_id, field, old, new, reason, admin_id):
    # Create order history entry
    history = OrderHistory(
        order_id=order_id,
        field_name=field,
        old_value=str(old),
        new_value=str(new),
        reason=reason,
        changed_by=admin_id
    )
    
    # Save history
    create_order_history(history)
```


## Admin Commands

### 1. Issue Credit

**Command:** `/credit <username> <amount> [reason]`

**Examples:**
```
/credit john_doe 20.5 Defective bottles
/credit @johndoe 50 Customer dissatisfaction
```

**Workflow:**
1. Admin enters command
2. System validates customer exists using the existing customer matching code
3. System validates amount is positive
4. Show confirmation with:
   - Customer name
   - Credit amount
   - Current credit balance
   - New credit balance after crediting
   - Reason
5. Admin confirms
6. System creates credit transaction
7. System updates customer credit balance
8. System notifies customer
9. System confirms to admin

**Alternative Flow (Button-based):**
1. Admin uses `/credit` without args
2. System prompts for username input
3. Admin enters username
4. System requests amount
5. Admin enters amount
6. System requests reason
7. Admin enters reason
8. Confirmation and execution as above

### 2. View Customer Credit

**Command:** `/credit_balance <username>`

**Examples:**
```
/credit_balance john_doe
/credit_balance @johndoe
```

**Output:**
```
💰 Credit Balance for John Doe (@johndoe)

Current Balance: €45.50
Total Credits Issued: €120.00
Total Credits Used: €74.50

Recent Transactions:
• 2024-01-10: +€20.00 (CREDIT_ISSUED) - Defective bottles
• 2024-01-08: -€30.00 (APPLIED) - Applied to delivery
• 2024-01-05: +€25.50 (CREDIT_ISSUED) - Goodwill gesture

[View All Transactions] [Adjust Balance]
```

### 3. Adjust Credit Balance

**Command:** `/adjust_credit <username> <amount> <reason>`

**Examples:**
```
/adjust_credit john_doe +10.00 Goodwill gesture
/adjust_credit john_doe -5.00 Correction for overpayment
```

**Workflow:**
1. Admin enters command
2. System validates customer exists
3. Show confirmation with current and new balance
4. Admin confirms
5. System creates ADJUSTMENT transaction
6. System updates customer credit balance
7. System notifies customer (optional, based on amount)
8. System confirms to admin

### 4. List Customers with Credit

**Command:** `/list_credits [min_amount]`

**Examples:**
```
/list_credits
/list_credits 20
```

**Output:**
```
💰 Customers with Credit Balance

1. John Doe (@johndoe) - €45.50
2. Jane Smith (@janesmith) - €30.00
3. Bob Wilson - €15.75

Total: 3 customers, €91.25 in credits

[Export CSV] [View Details]
```

### 5. Credit Transaction History

**Command:** `/credit_history <username> [days]`

**Examples:**
```
/credit_history john_doe
/credit_history john_doe 30
```

**Output:** Paginated list of all credit transactions for customer


## Customer Commands

### 1. View Credit Balance

**Command:** `/my_credit`

**Output:**
```
💰 Your Credit Balance

Current Balance: €45.50

This credit will be automatically applied to your next delivery.

Recent Credits:
• 2024-01-10: +€20.00 - Defective bottles
• 2024-01-05: +€25.50 - Goodwill gesture

Recent Usage:
• 2024-01-08: -€30.00 - Applied to delivery

Questions? Contact admin.
```

## Delivery Overview Integration

### Modified Delivery Overview Flow

**Current Flow:**
1. Admin runs `/send_overviews`
2. System calculates total for each customer
3. System sends overview with payment link
4. Orders marked as AWAITING_PAYMENT

**New Flow with Credits:**
1. Admin runs `/send_overviews`
2. System calculates total for each customer
3. **System checks customer credit balance**
4. **System calculates adjusted payment amount:**
   - If credit >= total: Payment = €0, remaining credit carried forward
   - If credit < total: Payment = total - credit, credit depleted
5. **System creates APPLIED transaction for credit used**
6. System sends overview with:
   - Original total
   - Credit applied
   - Adjusted payment amount
   - Remaining credit (if any)
   - Payment link (if payment > 0)
7. Orders marked as AWAITING_PAYMENT

### Enhanced Delivery Overview Message

Review the current messaging and integration the credits into those.
**Scenario 1: Credit < Total**
```
📦 Delivery Overview

Ready for Pickup:
• 3x Brewery IPA - €30.00
• 2x Stout Beer - €20.00

Subtotal: €50.00
Credit Applied: -€20.00
─────────────────
Total to Pay: €30.00

💰 Remaining Credit: €0.00

Payment Link: [link]
```

**Scenario 2: Credit > Total**
```
📦 Delivery Overview

Ready for Pickup:
• 3x Brewery IPA - €30.00
• 2x Stout Beer - €20.00

Subtotal: €50.00
Credit Applied: -€50.00
─────────────────
Total to Pay: €0.00

💰 Remaining Credit: €10.00

✅ No payment needed! Your credit covers this delivery.
Your remaining credit will be applied to future orders.
```

**Scenario 3: No Credit**
```
📦 Delivery Overview

Ready for Pickup:
• 3x Brewery IPA - €30.00
• 2x Stout Beer - €20.00

Total to Pay: €50.00

Payment Link: [link]
```


## Business Logic & Rules

### Credit Application Algorithm
```python
def apply_credit_to_delivery(customer_id: str, delivery_total: Decimal) -> Dict:
    """Apply credit when orders transition LABELING_COMPLETED → AWAITING_PAYMENT"""
    credit_balance = get_customer_credit_balance(customer_id)
    
    if credit_balance <= 0:
        return {
            'original_total': delivery_total,
            'credit_applied': Decimal('0.0'),
            'payment_required': delivery_total,
            'remaining_credit': Decimal('0.0')
        }
    
    credit_to_apply = min(credit_balance, delivery_total)
    payment_required = delivery_total - credit_to_apply
    remaining_credit = credit_balance - credit_to_apply
    
    # Create APPLIED transaction
    create_credit_transaction(
        customer_id=customer_id,
        transaction_type='APPLIED',
        amount=-credit_to_apply,  # Negative for usage
        balance_before=credit_balance,
        balance_after=remaining_credit,
        reason=f"Applied to delivery"
    )
    
    # Update customer credit balance
    update_customer_credit_balance(customer_id, remaining_credit)
    
    return {
        'original_total': delivery_total,
        'credit_applied': credit_to_apply,
        'payment_required': payment_required,
        'remaining_credit': remaining_credit
    }
```

## Edge Cases & Handling

### 1. Credit Issued for Wrong Customer
**Handling:** Admin manually reverses using adjustment transaction with audit trail

### 2. Credit Applied but Delivery Fails
**Handling:** Credit remains applied, customer contacts admin for manual resolution

### 3. Customer Deletion with Credit Balance
**Handling:** System allows deletion, does not require credit settlement first

### 4. Concurrent Credit Updates
**Handling:** DynamoDB conditional updates ensure atomic operations

### 5. Delivery Overview Regeneration
**Handling:** Not applicable - delivery overviews cannot be regenerated in current system. Credits are only applied during LABELING_COMPLETED → AWAITING_PAYMENT transition.


## Implementation Details

### Files to Create

1. **`src/models/entities.py`** - Add new dataclasses:
   - `CustomerCredit`
   - `CreditTransaction`
   - `OrderHistory`

2. **`src/services/credit_service.py`** - New service:
   - `get_customer_credit_balance(customer_id)`
   - `create_credit_transaction(transaction_data)`
   - `apply_credit_to_delivery(customer_id, delivery_total)`
   - `issue_credit(customer_id, amount, reason, admin_id)`
   - `adjust_credit_balance(customer_id, amount, reason, admin_id)`
   - `get_credit_transactions(customer_id, limit, days)`
   - `get_customers_with_credit(min_amount)`

3. **`src/services/audit_service.py`** - New service:
   - `log_order_change(order_id, admin_id, field_name, old_value, new_value, reason, credit_transaction_id)`
   - `get_order_history(order_id, limit)`
   - `get_changes_by_admin(admin_id, days)`

4. **`src/handlers/admin/credit_commands.py`** - New handler:
   - `handle_credit(chat_id, args)`
   - `handle_credit_balance(chat_id, args)`
   - `handle_adjust_credit(chat_id, args)`
   - `handle_list_credits(chat_id, args)`
   - `handle_credit_history(chat_id, args)`

5. **`src/handlers/customer/credit_commands.py`** - New handler:
   - `handle_my_credit(chat_id, user_id)`

### Files to Modify

1. **`src/services/database.py`** - Add methods:
   - `create_customer_credit(credit)`
   - `get_customer_credit(customer_id)`
   - `update_customer_credit(customer_id, updates)`
   - `create_credit_transaction(transaction)`
   - `get_credit_transactions_by_customer(customer_id)`
   - `get_customers_with_credit_balance(min_amount)`
   - `create_order_history(history)`
   - `get_order_history(order_id)`
   - `get_order_history_by_admin(admin_id, days)`

2. **`src/handlers/admin/delivery_overview_handler.py`** - Modify:
   - `_send_delivery_overview()` - Add credit calculation and application
   - Update message template to show credit information

3. **`src/handlers/customer/order_commands.py`** - Modify:
   - `handle_my_orders()` - Show credit information

4. **`src/services/command_router.py`** - Add new commands:
   - `/credit` → admin credit handler
   - `/credit_balance` → admin credit handler
   - `/adjust_credit` → admin credit handler
   - `/list_credits` → admin credit handler
   - `/credit_history` → admin credit handler
   - `/my_credit` → customer credit handler

5. **`template.yaml`** - Add new DynamoDB tables:
   - `CustomerCreditsTable`
   - `CreditTransactionsTable`
   - `OrderHistoryTable`

6. **`src/translations/en.json` & `nl.json`** - Add translation keys:
   - Credit balance messages
   - Credit notifications
   - Delivery overview credit text
   - Admin confirmation messages
   - Error messages

### Database Indexes

**CustomerCreditsTable:**
- Primary Key: `customer_id`
- No GSI needed (single-item lookups only)

**CreditTransactionsTable:**
- Primary Key: `transaction_id`
- GSI: `customer-index` on `customer_id` (for transaction history)
- GSI: `created-at-index` on `created_at` (for recent transactions, optional)

**OrderHistoryTable:**
- Primary Key: `history_id`
- GSI: `order-index` on `order_id` (for order audit trail)
- TTL: `ttl` attribute (2-year retention, automatic cleanup)

### Admin Panel Integration

Add new section: **💰 Credits **

Buttons:
- Issue Credit
- View Credit Balances
- Adjust Credit
- Credit History
- Export Credits Report

### Notification Messages

**Customer Credit Issued Notification:**
```
💰 Credit Issued

You have received a credit of €20.00

Reason: Defective bottles

Your new credit balance: €45.50

This credit will be automatically applied to your next delivery.

Questions? Contact admin.
```

**Admin Credit Confirmation:**
```
✅ Credit Issued Successfully

Customer: John Doe (@johndoe)
Amount: €20.00
Reason: Defective bottles

Previous Balance: €25.50
New Balance: €45.50

Customer has been notified.
```

## Testing Requirements

### Unit Tests

1. **Credit Service Tests**
   - Test credit balance retrieval
   - Test credit transaction creation
   - Test credit application with various scenarios
   - Test credir issuance
   - Test credit adjustment
   - Test concurrent credit updates

2. **Credit Calculation Tests**
   - Credit < delivery total
   - Credit > delivery total
   - Credit = delivery total
   - Zero credit
   - Multiple credits applied

3. **Credit Validation Tests**
   - Credit amount validation
   - Order status validation
   - Duplicate credit prevention
   - Credit > order total handling

### Integration Tests

1. **Full Credit Workflow**
   - Issue credit → verify credit balance → apply to delivery → verify payment

2. **Multi-Delivery Credit Usage**
   - Large credit → multiple deliveries → credit depletion

3. **Guest User Credit**
   - Issue credit to guest → verify credit tracking

4. **Concurrent Operations**
   - Simultaneous credit applications
   - Credit during delivery processing

### Manual Testing Scenarios

1. Issue credit for completed order
2. Issue credit for cancelled order
3. Apply credit to delivery (credit < total)
4. Apply credit to delivery (credit > total)
5. Adjust credit balance (add/subtract)
6. View credit history
7. Customer views credit balance
8. Export credits report


## Query Volume Analysis & Caching Strategy

### Query Patterns

**High Frequency (Cache Recommended):**
1. **Customer credit balance lookup** - During delivery overview generation
   - Frequency: Once per customer per delivery batch (50-100 customers per batch)
   - Pattern: Batch processing, sequential reads
   - Cache benefit: HIGH

2. **Customer views own credit** - `/my_credit` command
   - Frequency: Low (occasional customer queries)
   - Pattern: Individual, sporadic
   - Cache benefit: LOW

**Medium Frequency (Cache Optional):**
3. **Admin views customer credit** - `/credit_balance` command
   - Frequency: Medium (admin checking before credit/adjustment)
   - Pattern: Individual, sporadic
   - Cache benefit: MEDIUM

4. **List customers with credit** - `/list_credits` command
   - Frequency: Low (admin reporting)
   - Pattern: Full scan required
   - Cache benefit: LOW (scan operation)

**Low Frequency (No Cache Needed):**
5. **Credit transaction history** - `/credit_history` command
   - Frequency: Very low (admin audit)
   - Pattern: Historical query
   - Cache benefit: NONE

6. **Issue credit** - `/credit` command
   - Frequency: Low (exception handling)
   - Pattern: Write operation
   - Cache benefit: NONE (invalidates cache)

### Caching Recommendation: YES (Selective)

**Cache Only:** Customer credit balance (`current_balance` field)

**Rationale:**
1. **Delivery overview bottleneck** - Processing 50-100 customers sequentially requires 50-100 DynamoDB reads
2. **Read-heavy pattern** - Credit balance is read frequently, updated infrequently
3. **Simple data** - Single Decimal value, easy to cache and invalidate
4. **Cost savings** - Reduces DynamoDB read capacity units during batch processing

### Caching Implementation

**Cache Service:** `src/services/credit_cache.py`

```python
class CreditCache:
    """In-memory cache for customer credit balances"""
    
    _cache = {}  # {customer_id: {'balance': Decimal, 'timestamp': datetime}}
    _ttl_seconds = 300  # 5 minutes
    
    @classmethod
    def get_balance(cls, customer_id: str, db_service) -> Optional[Decimal]:
        """Get credit balance from cache or database"""
        # Check cache
        if customer_id in cls._cache:
            cached = cls._cache[customer_id]
            age = (datetime.now(UTC) - cached['timestamp']).total_seconds()
            if age < cls._ttl_seconds:
                return cached['balance']
        
        # Cache miss - fetch from database
        credit = db_service.get_customer_credit(customer_id)
        balance = credit.current_balance if credit else Decimal('0.0')
        
        # Update cache
        cls._cache[customer_id] = {
            'balance': balance,
            'timestamp': datetime.now(UTC)
        }
        
        return balance
    
    @classmethod
    def invalidate(cls, customer_id: str):
        """Invalidate cache for specific customer"""
        if customer_id in cls._cache:
            del cls._cache[customer_id]
    
    @classmethod
    def invalidate_all(cls):
        """Clear entire cache"""
        cls._cache.clear()
```

**Cache Invalidation Points:**
1. After issuing credit → `CreditCache.invalidate(customer_id)`
2. After adjusting credit → `CreditCache.invalidate(customer_id)`
3. After applying credit to delivery → `CreditCache.invalidate(customer_id)`
4. After any credit transaction → `CreditCache.invalidate(customer_id)`

**Usage Pattern:**
```python
# In delivery_overview_handler.py
def _send_delivery_overview(self, customer_data: Dict, payment_link: str):
    # Use cached balance
    credit_balance = CreditCache.get_balance(customer_id, self.db)
    
    # Apply credit logic...
    
    # Invalidate after applying
    CreditCache.invalidate(customer_id)
```

### Cache Characteristics

**TTL:** 5 minutes
- Short enough to prevent stale data
- Long enough to benefit batch processing
- Invalidation ensures consistency

**Storage:** In-memory (Lambda execution context)
- No external cache service needed (Redis, ElastiCache)
- Simple implementation
- Zero additional cost
- Automatic cleanup on Lambda cold start

**Consistency:** Strong (via invalidation)
- Every write operation invalidates cache
- Reads always get fresh data after writes
- No eventual consistency issues

### Performance Impact

**Without Cache:**
- 100 customers × 1 DynamoDB read = 100 read operations
- Cost: ~$0.000125 per batch (at $0.25 per million reads)
- Latency: ~100ms per customer (sequential)
- Total batch time: ~10 seconds

**With Cache:**
- First batch: 100 reads (cache miss)
- Subsequent batches within 5 min: 0 reads (cache hit)
- Cost: ~$0.000125 per 5 minutes
- Latency: <1ms per customer (memory access)
- Total batch time: ~1 second

**Savings:**
- 80-90% reduction in DynamoDB reads during batch processing
- 90% reduction in batch processing time
- Minimal code complexity
- No additional infrastructure

### Alternative: No Cache

**Arguments Against Caching:**
1. **Low query volume** - If deliveries are infrequent (weekly/monthly), caching benefit is minimal
2. **Complexity** - Cache invalidation adds code complexity
3. **Stale data risk** - If invalidation fails, customers see wrong balance
4. **Lambda stateless** - Cache doesn't persist across Lambda invocations

**When to Skip Cache:**
- Delivery batches < 20 customers
- Deliveries less than weekly
- Team prefers simplicity over optimization

### Recommendation: Implement Cache

**Justification:**
1. **Batch processing is the primary use case** - 50-100 customers per batch
2. **Simple implementation** - ~50 lines of code
3. **Strong consistency** - Invalidation on every write
4. **Zero cost** - No external services
5. **Significant performance gain** - 10x faster batch processing
6. **Future-proof** - Scales with customer growth

**Implementation Priority:** Medium
- Not critical for MVP
- Add after core credit functionality works
- Easy to add later without breaking changes

### Cache Monitoring

**Metrics to Track:**
- Cache hit rate (target: >80% during batch processing)
- Cache invalidation count (should match write operations)
- Average batch processing time (target: <2 seconds for 100 customers)

**Logging:**
```python
logger.info(f"Credit cache hit for customer {customer_id}")
logger.info(f"Credit cache miss for customer {customer_id}")
logger.info(f"Credit cache invalidated for customer {customer_id}")
```

### Cache Testing

**Test Scenarios:**
1. Cache miss on first read
2. Cache hit on subsequent read within TTL
3. Cache expiry after TTL
4. Cache invalidation after credit
5. Cache invalidation after credit application
6. Concurrent access (multiple Lambda invocations)


## Business Rules & Decisions

### Credit Application Timing
**DECISION:** Credits are applied automatically only when orders transition from LABELING_COMPLETED → AWAITING_PAYMENT status.
- Credits are NOT applied to existing AWAITING_PAYMENT orders
- Credits are NOT applied when manually regenerating delivery overviews
- Single trigger point ensures consistency and prevents double-application
- **Credit application happens AFTER order status transition** (Decision #31)
- **If credit application fails, order remains AWAITING_PAYMENT and admin manually resolves** (Decision #32)
- **No compensating transactions or intermediate statuses** (Decision #33)

### Confirmed Decisions

**Credit Application:**
1. **Automatic Application:** YES - Credits always applied automatically (no customer consent required)
2. **Customer Opt-Out:** NO - Customers cannot opt-out of credit application
3. **Guest Users:** YES - Track credit, admin manually settles
4. **Delivery Overview Regeneration:** N/A - Not possible in current system

**Notifications:**
5. **Credit Issued:** YES - Immediate notification to customer
6. **Credit Applied:** NO - Only shown in delivery overview (no separate notification)
7. **Admin Notification:** NO - Admin not notified when customer views balance

**Reporting:**
8. **Monthly Reports:** NO - On-demand reports only
9. **Metrics:** Basic metrics (total outstanding, issued, applied)

**Technical:**
10. **Caching:** YES - 5-minute TTL in-memory cache
11. **Concurrency:** DynamoDB conditional updates with retry logic

### Confirmed Decisions (Additional)

12. **Credit Export:** YES - Separate `/export_credits` command for CSV export (8 fields: customer_id, customer_name, username, current_balance, total_issued, total_used, last_transaction_date, is_guest)
13. **Transaction Immutability:** YES - Never delete/modify transactions, use adjustment transactions for corrections
14. **Amount Precision:** 2 decimal places (€0.01)
15. **Maximum Balance:** NO - No limit on customer credit balance
16. **Customer Deletion:** ALLOW - Customer deletion allowed regardless of credit balance, audit log maintains historical record
17. **Wrong Customer Credit:** Manual reversal via adjustment transactions (negative for wrong customer, positive for correct customer)
18. **Failed Delivery:** Credit remains applied, admin manually resolves if needed
19. **Credit Expiry:** NO - Credits never expire
20. **Credit Issuance:** Credits are always independent (no order linkage)
21. **Guest User Credits:** Credits apply automatically to deliveries; admin receives delivery overview with credit info and manually relays to guest via contact method
22. **Partial Delivery Credits:** Credits apply to delivered items only (not delayed items)
23. **Credit Notifications:** Always notify customers for all credit transactions (CREDIT_ISSUED, ADJUSTMENT, MANUAL_ADD, MANUAL_SUBTRACT)
24. **Negative Balance:** System warns but allows admin to confirm and proceed with negative balance
25. **Multiple Credits Display:** Show separate line items with dates in delivery overview for maximum transparency
26. **Batch Processing Rollback:** No rollback - credit remains applied even if overview send fails, admin manually resolves
27. **Customer Credit History:** `/my_credit` shows last 10 transactions only; admin has full access via `/credit_history`
28. **Order List Display:** Do not mention credit in `/list_my_orders`; `/help` shows `/my_credit` command
29. **Concurrency:** Not applicable - single admin, no special concurrency handling needed
30. **Cancelled Order Credits:** Credits are never automatically reversed; admin manually adjusts if needed.
31. **Credit Application Timing:** Credit application happens AFTER order status transition to AWAITING_PAYMENT
32. **Failed Credit Application:** If credit application fails, order remains AWAITING_PAYMENT and admin manually resolves
33. **No Compensating Transactions:** No automatic rollback or intermediate statuses for credit application failures

---

## Open Questions (Added from Viability Review)

### Specification Completion
- **Q1:** ✅ RESOLVED - ALL credit issuance is manual, regardless of cancellation reason. Credits are never automatically issued or reversed when orders are cancelled.
- **Q2:** ✅ RESOLVED - No additional decisions beyond #30
- **Q3:** ✅ RESOLVED - No unresolved edge cases

### Credit Application Timing
- **Q4:** ✅ RESOLVED - Credit application happens AFTER status transition to AWAITING_PAYMENT. Order status is updated first, then credit is applied.
- **Q5:** ✅ RESOLVED - NO rollback. If credit application fails, order status remains AWAITING_PAYMENT and admin manually resolves.
- **Q6:** ✅ RESOLVED - NO atomic transaction. Status update and credit application are separate sequential operations.

### Batch Processing Rollback
- **Q7:** ✅ RESOLVED - NO pending credit application state. Admin relies on error messages to identify failed credit applications.
- **Q8:** ✅ RESOLVED - NO automatic reversal. Credit remains applied even if delivery overview send fails, admin manually resolves (per Decision #26).
- **Q9:** ✅ RESOLVED - No threshold. Process all customers regardless of failure rate. Admin is notified per-customer using `admin_overview_sent_failed` translation key.
- **Q10:** ✅ RESOLVED - YES. Admin receives aggregated summary at end of batch showing total customers, successful sends, failed sends, and list of failed customers with reasons.

### Guest User Credit Workflow
- **Q11:** ✅ RESOLVED - YES. Guest delivery overviews in admin message include credit balance at the top.
- **Q12:** ✅ RESOLVED - Credit application is already part of delivery overview message. For guest users, show remaining credit balance in admin message ONLY if balance is non-zero (positive or negative).
- **Q13:** ✅ RESOLVED - Batch summary shows: (1) count of successfully notified users, (2) failed users section with details (if any), (3) guest users section with full overviews (if any). Omit section headers when section is empty.

### Caching Strategy
- **Q14:** ✅ RESOLVED - Use in-memory caching (not DynamoDB DAX). Zero cost, simple implementation.
- **Q15:** ✅ RESOLVED - Implement caching in Phase 1 (MVP).
- **Q16:** ✅ RESOLVED - 1 Lambda instance during batch processing (sequential). Cache will be effective within single batch.
- **Q17:** ✅ RESOLVED - YES. Pre-load credit balances into cache before processing batch to ensure cache hits.

### Negative Balance Safeguards
- **Q18:** ✅ RESOLVED - Warning message: "⚠️ Creating a negative balance. Continue? Yes/No"
- **Q19:** ✅ RESOLVED - NO maximum negative balance limit.
- **Q20:** ✅ RESOLVED - NO admin alerts/reports for negative balances.
- **Q21:** ✅ RESOLVED - YES. Reason field is mandatory when creating negative balance.

### Database Design
- **Q22:** ✅ RESOLVED - NO GSI on CreditTransaction.created_by (single admin only).
- **Q23:** ✅ RESOLVED - NO GSI on CustomerCredit.current_balance (table scan acceptable for infrequent queries).

### Command Integration
- **Q24:** ✅ RESOLVED - YES. Add credit commands to `/admin` panel with button-based interface.
- **Q25:** ✅ RESOLVED - YES. Add `/my_credit` to customer help menu.
- **Q26:** ✅ RESOLVED - NO. Do not show credit balance in `/list_my_orders` output (per Decision #28).

### Translation Keys
- **Q27:** ✅ RESOLVED - Create translation key mapping during implementation (not now).
- **Q28:** ✅ RESOLVED - Amazon Q will provide Dutch translations.
- **Q29:** ✅ RESOLVED - YES. Follow existing tone/style guide.

### Correction Workflow
- **Q30:** ✅ RESOLVED - NO `/transfer_credit` command. Use `/adjust_credit` twice manually.
- **Q31:** ✅ RESOLVED - NO separate transaction type for corrections. Use ADJUSTMENT type.
- **Q32:** ✅ RESOLVED - NO automatic validation. Admin manually ensures correction transactions balance.

### Partial Delivery Logic
- **Q33:** ✅ RESOLVED - Out of scope. Partial delivery price recalculation not part of credit system.
- **Q34:** ✅ RESOLVED - Out of scope. Delayed item handling not part of credit system.
- **Q35:** ✅ RESOLVED - Not relevant. Credits apply to delivered orders as specified in Decision #22.

### Performance
- **Q36:** ✅ RESOLVED - Current batch processing time: ~10 seconds for 100 customers.
- **Q37:** ✅ RESOLVED - NO parallel processing for batch sends.
- **Q38:** ✅ RESOLVED - NO progress indicators for long batches.

### Testing
- **Q39:** ✅ RESOLVED - YES. Use TDD approach (create test files with failing tests first).
- **Q40:** ✅ RESOLVED - YES. Add credit system to end-to-end test plan.
- **Q41:** ✅ RESOLVED - 80% minimum test coverage required.

### Implementation Scope
- **Q42:** ✅ RESOLVED - NO scope reduction. Implement full MVP including caching and reporting.
- **Q43:** ✅ RESOLVED - NO smaller increments. Implement complete Phase 1 functionality.
- **Q44:** ✅ RESOLVED - Flexible timeline. Estimated 60-80 hours total (3-8 weeks depending on availability).

### Deployment Strategy
- **Q45:** ✅ RESOLVED - NO feature flag.
- **Q46:** ✅ RESOLVED - NO subset testing. Deploy to full environment.
- **Q47:** ✅ RESOLVED - NO formal rollback plan. Disable commands via router if issues arise (per spec Rollback Plan section).

### Database Design (Future-Proofing)
- **Q48:** ⚠️ OPEN - Should we add GSI on `CreditTransaction.created_by` for future-proofing, even if single admin today? (Viability Review: Recommended for multi-admin scenarios)
- **Q49:** ⚠️ OPEN - Should we add GSI on `CustomerCredit.current_balance` to avoid table scans for `/list_credits`? (Viability Review: Recommended when customer count exceeds 1000)

### Credit Application Timing (CRITICAL)
- **Q50:** ✅ RESOLVED - Credit application happens AFTER order status transition. If credit application fails, order remains AWAITING_PAYMENT and admin manually resolves.
- **Q51:** ✅ RESOLVED - NO compensating transactions. Failed credit applications require manual admin cleanup.
- **Q52:** ✅ RESOLVED - NO intermediate status. Direct transition LABELING_COMPLETED → AWAITING_PAYMENT is correct.

### Batch Processing Enhancements
- **Q53:** ⚠️ OPEN - Should we add batch progress indicators (e.g., "Processing 25/100...")? (Viability Review: Recommended for batches >50 customers)
- **Q54:** ⚠️ OPEN - Should we implement batch checkpointing to resume failed batches? (Viability Review: Recommended for batches >200 customers)
- **Q55:** ⚠️ OPEN - Should guest user overviews show credit balance even when zero (for consistency)? (Viability Review: Minor UX improvement)

### Caching Enhancements
- **Q56:** ⚠️ OPEN - Should we pre-warm cache before batch processing (load all customer credits upfront)? (Viability Review: Recommended for Phase 1)
- **Q57:** ⚠️ OPEN - Should we add cache hit/miss metrics for monitoring? (Viability Review: Nice to have)

### Technical Implementation Details
- **Q58:** ⚠️ OPEN - Should we use DynamoDB TransactWriteItems for atomic credit+order updates? (Viability Review: Would eliminate race conditions)
- **Q59:** ⚠️ OPEN - What retry strategy should we use for conditional update failures? (Viability Review: Need to specify exponential backoff parameters)

### Translation & Documentation
- **Q60:** ⚠️ OPEN - Should we create a translation key mapping document now or during implementation? (Viability Review: Recommended before implementation)

### Admin UX Improvements
- **Q61:** ⚠️ OPEN - Should we add `/undo_credit` command for quick reversal of last credit transaction? (Viability Review: Recommended for Phase 2)
- **Q62:** ⚠️ OPEN - Should negative balance warnings require explicit confirmation (two-step process)? (Viability Review: Recommended to prevent accidents)

### Testing Strategy
- **Q63:** ⚠️ OPEN - Should we add performance benchmarks for batch processing with credits? (Viability Review: Nice to have)
- **Q64:** ⚠️ OPEN - Should we add chaos testing (simulate DynamoDB failures, Lambda timeouts)? (Viability Review: Nice to have)

---

## Questions Status Summary

**Total Questions:** 64
**Resolved:** 50
**Critical Open:** 0
**Important Open:** 8 (Q48, Q49, Q53, Q54, Q58, Q59, Q61, Q62)
**Nice to Have Open:** 6 (Q55, Q56, Q57, Q60, Q63, Q64)

**Status:** ✅ CRITICAL QUESTIONS RESOLVED - Ready for implementation with open questions to be decided during development

**See:** `docs/credit-system-viability-review.md` for detailed analysis and recommendations

---

## Implementation Scope
- **Q42:** ✅ RESOLVED - NO scope reduction. Implement full MVP including caching and reporting.
- **Q43:** ✅ RESOLVED - NO smaller increments. Implement complete Phase 1 functionality.
- **Q44:** ✅ RESOLVED - Flexible timeline. Estimated 60-80 hours total (3-8 weeks depending on availability).

### Deployment Strategy
- **Q45:** Should we implement feature flag for credit system?
- **Q46:** Should we test with subset of customers first?
- **Q47:** Should we have rollback plan if issues discovered?

--- are never automatically reversed; admin manually adjusts if needed

## Implementation Phases

### Phase 1: Core Credit System (MVP)
**Estimated Time:** 17-22 hours
**TDD Approach:** Write failing tests first, then implement code to pass tests
**Status:** ✅ Tasks 1.1-1.10 COMPLETED

#### Task 1.1: Database Schema & Infrastructure (2-3 hours) ✅ COMPLETED
**Commit:** `feat: add credit system database tables to CloudFormation`

- Add 3 new DynamoDB tables to `template.yaml`:
  - `CustomerCreditsTable`
  - `CreditTransactionsTable`
  - `OrderHistoryTable`
- Add IAM permissions for Lambda to access new tables
- Deploy infrastructure only (no code changes)

**Files:** `template.yaml`
**Note:** Infrastructure setup - no tests needed

#### Task 1.2: Data Models (1-2 hours) ✅ COMPLETED
**Commit:** `feat: add credit system data models`

- Add `CustomerCredit` dataclass to `src/models/entities.py`
- Add `CreditTransaction` dataclass
- Add `OrderHistory` dataclass
- No business logic, just data structures

**Files:** `src/models/entities.py`
**Note:** Data models - no tests needed (dataclasses)

#### Task 1.3: Database Access Layer (2-3 hours) ✅ COMPLETED
**Commit:** `test: add failing tests for credit database operations`
**Commit:** `feat: implement database methods for credit system`

**TDD Steps:**
1. Create `tests/test_database_credit.py` with failing tests:
   - Test `create_customer_credit()`
   - Test `get_customer_credit()`
   - Test `update_customer_credit()`
   - Test `create_credit_transaction()`
   - Test `get_credit_transactions_by_customer()`
   - Test `create_order_history()`
   - Test `get_order_history()`
2. Run tests (should fail)
3. Implement methods in `src/services/database.py`
4. Run tests (should pass)

**Files:** `tests/test_database_credit.py`, `src/services/database.py`

#### Task 1.4: Credit Service - Core Logic (3-4 hours) ✅ COMPLETED
**Commit:** `test: add failing tests for core credit service`
**Commit:** `feat: implement core credit service logic`

**TDD Steps:**
1. Create `tests/test_credit_service.py` with failing tests:
   - Test `get_customer_credit_balance()` with existing credit
   - Test `get_customer_credit_balance()` with no credit (returns 0)
   - Test `create_credit_transaction()`
   - Test `_update_customer_credit_balance()`
2. Run tests (should fail)
3. Create `src/services/credit_service.py` and implement methods
4. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `src/services/credit_service.py`

#### Task 1.5: Credit Service - Issue Credit (2-3 hours) ✅ COMPLETED
**Commit:** `test: add failing tests for issue credit functionality`
**Commit:** `feat: add issue credit functionality`

**TDD Steps:**
1. Add to `tests/test_credit_service.py`:
   - Test `issue_credit()` with valid amount
   - Test `issue_credit()` with invalid amount (negative, zero)
   - Test `issue_credit()` with non-existent customer
   - Test transaction creation and balance update
2. Run tests (should fail)
3. Implement `issue_credit()` in `src/services/credit_service.py`
4. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `src/services/credit_service.py`

#### Task 1.6: Credit Service - Apply Credit (2-3 hours) ✅ COMPLETED
**Commit:** `test: add failing tests for credit application logic`
**Commit:** `feat: add credit application logic for deliveries`

**TDD Steps:**
1. Add to `tests/test_credit_service.py`:
   - Test `apply_credit_to_delivery()` with credit < total
   - Test `apply_credit_to_delivery()` with credit > total
   - Test `apply_credit_to_delivery()` with credit = total
   - Test `apply_credit_to_delivery()` with zero credit
   - Test balance updates and transaction creation
2. Run tests (should fail)
3. Implement `apply_credit_to_delivery()` in `src/services/credit_service.py`
4. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `src/services/credit_service.py`

#### Task 1.7: Audit Service (2 hours) ✅ COMPLETED
**Commit:** `test: add failing tests for audit service`
**Commit:** `feat: add audit service for order history tracking`

**TDD Steps:**
1. Create `tests/test_audit_service.py` with failing tests:
   - Test `log_order_change()` creates history entry
   - Test `get_order_history()` retrieves entries
   - Test TTL is set correctly
2. Run tests (should fail)
3. Create `src/services/audit_service.py` and implement methods
4. Run tests (should pass)

**Files:** `tests/test_audit_service.py`, `src/services/audit_service.py`

#### Task 1.8: Translation Keys (1 hour) ✅ COMPLETED
**Commit:** `feat: add translation keys for credit system`

- Add credit-related keys to `src/translations/en.json`
- Add credit-related keys to `src/translations/nl.json`
- Basic keys only (notifications, errors, confirmations)

**Files:** `src/translations/en.json`, `src/translations/nl.json`
**Note:** Translation files - no tests needed

#### Task 1.9: Admin Command - Issue Credit (Basic) (2-3 hours) ✅ COMPLETED
**Commit:** `test: add failing tests for /credit command`
**Commit:** `feat: add basic /credit command for admins`

**TDD Steps:**
1. Create `tests/test_admin_credit_commands.py` with failing tests:
   - Test `/credit` with valid input
   - Test `/credit` with invalid username
   - Test `/credit` with invalid amount
   - Test `/credit` with missing reason
   - Test command routing
2. Run tests (should fail)
3. Create `src/handlers/admin/credit_commands.py` and implement
4. Add to command router
5. Run tests (should pass)

**Files:** `tests/test_admin_credit_commands.py`, `src/handlers/admin/credit_commands.py`, `src/services/command_router.py`

#### Task 1.10: Customer Command - View Credit (1-2 hours) ✅ COMPLETED
**Commit:** `test: add failing tests for /my_credit command`
**Commit:** `feat: add /my_credit command for customers`

**TDD Steps:**
1. Create `tests/test_customer_credit_commands.py` with failing tests:
   - Test `/my_credit` with existing credit
   - Test `/my_credit` with zero credit
   - Test `/my_credit` displays recent transactions
   - Test command routing
2. Run tests (should fail)
3. Create `src/handlers/customer/credit_commands.py` and implement
4. Add to command router
5. Run tests (should pass)

**Files:** `tests/test_customer_credit_commands.py`, `src/handlers/customer/credit_commands.py`, `src/services/command_router.py`

#### Task 1.11: Delivery Overview Integration (3-4 hours)
**Commit:** `test: add failing tests for delivery overview credit integration`
**Commit:** `feat: integrate credit application into delivery overviews`

**TDD Steps:**
1. Create `tests/test_delivery_overview_credit.py` with failing tests:
   - Test overview with credit < total
   - Test overview with credit > total
   - Test overview with credit = total
   - Test overview with zero credit
   - Test message formatting with credit info
2. Run tests (should fail)
3. Modify `src/handlers/admin/delivery_overview_handler.py`
4. Run tests (should pass)

**Files:** `tests/test_delivery_overview_credit.py`, `src/handlers/admin/delivery_overview_handler.py`

#### Task 1.12: Credit Notifications (1-2 hours)
**Commit:** `test: add failing tests for credit notifications`
**Commit:** `feat: add customer notifications for credit transactions`

**TDD Steps:**
1. Add to `tests/test_credit_service.py`:
   - Test notification sent when credit issued
   - Test notification content and formatting
   - Test notification failure handling
2. Run tests (should fail)
3. Add notification logic to `src/services/credit_service.py`
4. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `src/services/credit_service.py`

#### Task 1.13: Integration Tests (2-3 hours)
**Commit:** `test: add end-to-end integration tests for credit workflow`

**TDD Steps:**
1. Create `tests/integration/test_credit_workflow.py`:
   - Test full workflow: issue credit → apply to delivery → verify balance
   - Test multiple delivery scenarios with carry-forward
   - Test edge cases (credit > total, credit < total)
   - Test guest user credit workflow
2. Run integration tests
3. Fix any issues discovered
4. Verify 80% test coverage achieved

**Files:** `tests/integration/test_credit_workflow.py`

#### Task 1.14: Documentation (1 hour)
**Commit:** `docs: add credit system documentation`

- Update `README.md` with credit commands
- Add credit system overview
- Document admin and customer workflows

**Files:** `README.md`
**Note:** Documentation - no tests needed

**Phase 1 Summary:**
- **Total Tasks:** 14 atomic tasks
- **Estimated Time:** 17-22 hours
- **Average Task Size:** 1-3 hours each
- **TDD Approach:** Tests written before implementation for all business logic
- **Test Coverage Target:** 80% minimum

---

### Phase 2: Enhanced Admin Features
**Estimated Time:** 10-15 hours
**TDD Approach:** Write failing tests first, then implement code to pass tests

#### Task 2.1: Credit Adjustment Command (2-3 hours)
**Commit:** `test: add failing tests for /adjust_credit command`
**Commit:** `feat: add /adjust_credit command for admins`

**TDD Steps:**
1. Add to `tests/test_admin_credit_commands.py`:
   - Test `/adjust_credit` with positive adjustment
   - Test `/adjust_credit` with negative adjustment
   - Test `/adjust_credit` creating negative balance
   - Test validation and error handling
2. Run tests (should fail)
3. Add `adjust_credit_balance()` to `src/services/credit_service.py`
4. Implement `/adjust_credit` command in `src/handlers/admin/credit_commands.py`
5. Run tests (should pass)

**Files:** `tests/test_admin_credit_commands.py`, `src/services/credit_service.py`, `src/handlers/admin/credit_commands.py`

#### Task 2.2: List Customers with Credit (2-3 hours)
**Commit:** `test: add failing tests for /list_credits command`
**Commit:** `feat: add /list_credits command for admins`

**TDD Steps:**
1. Add to `tests/test_admin_credit_commands.py`:
   - Test `/list_credits` returns all customers with credit
   - Test `/list_credits` with min_amount filter
   - Test pagination
   - Test empty results
2. Run tests (should fail)
3. Add `get_customers_with_credit()` to `src/services/credit_service.py`
4. Implement `/list_credits` command
5. Run tests (should pass)

**Files:** `tests/test_admin_credit_commands.py`, `src/services/credit_service.py`, `src/handlers/admin/credit_commands.py`

#### Task 2.3: Credit Transaction History (2-3 hours)
**Commit:** `test: add failing tests for /credit_history command`
**Commit:** `feat: add /credit_history command for admins`

**TDD Steps:**
1. Add to `tests/test_admin_credit_commands.py`:
   - Test `/credit_history` retrieves transactions
   - Test `/credit_history` with days filter
   - Test pagination
   - Test transaction formatting
2. Run tests (should fail)
3. Add `get_credit_transactions()` to `src/services/credit_service.py`
4. Implement `/credit_history` command
5. Run tests (should pass)

**Files:** `tests/test_admin_credit_commands.py`, `src/services/credit_service.py`, `src/handlers/admin/credit_commands.py`

#### Task 2.4: Credit Balance View Command (1-2 hours)
**Commit:** `test: add failing tests for /credit_balance command`
**Commit:** `feat: add /credit_balance command for admins`

**TDD Steps:**
1. Add to `tests/test_admin_credit_commands.py`:
   - Test `/credit_balance` displays customer info
   - Test balance, totals, and recent transactions
   - Test action buttons
2. Run tests (should fail)
3. Implement `/credit_balance` command
4. Run tests (should pass)

**Files:** `tests/test_admin_credit_commands.py`, `src/handlers/admin/credit_commands.py`

#### Task 2.5: Admin Panel Integration (2-3 hours)
**Commit:** `test: add failing tests for admin panel credit integration`
**Commit:** `feat: integrate credit commands into admin panel`

**TDD Steps:**
1. Add to `tests/test_admin_panel.py`:
   - Test "💰 Credits" section appears
   - Test credit buttons (Issue, View, Adjust, History)
   - Test callback handlers
2. Run tests (should fail)
3. Modify `src/handlers/admin/admin_panel.py`
4. Add callback handlers
5. Run tests (should pass)

**Files:** `tests/test_admin_panel.py`, `src/handlers/admin/admin_panel.py`

#### Task 2.6: Enhanced Credit UI - Confirmation Dialogs (1-2 hours)
**Commit:** `test: add failing tests for credit confirmation dialogs`
**Commit:** `feat: add confirmation dialogs for credit operations`

**TDD Steps:**
1. Add to `tests/test_admin_credit_commands.py`:
   - Test confirmation dialog for `/credit`
   - Test confirmation dialog for `/adjust_credit`
   - Test before/after balance preview
   - Test cancel option
2. Run tests (should fail)
3. Add confirmation logic to `src/handlers/admin/credit_commands.py`
4. Run tests (should pass)

**Files:** `tests/test_admin_credit_commands.py`, `src/handlers/admin/credit_commands.py`

#### Task 2.7: Translation Keys - Phase 2 (1 hour)
**Commit:** `feat: add Phase 2 translation keys for credit system`

- Add adjustment-related keys
- Add list/history display keys
- Add admin panel button labels
- Add confirmation dialog keys

**Files:** `src/translations/en.json`, `src/translations/nl.json`
**Note:** Translation files - no tests needed

#### Task 2.8: Admin Workflow Tests (1-2 hours)
**Commit:** `test: add admin workflow integration tests`

**TDD Steps:**
1. Create `tests/integration/test_admin_credit_workflows.py`:
   - Test complete credit adjustment workflow
   - Test list credits with pagination
   - Test credit history retrieval
   - Test admin panel button interactions
2. Run integration tests
3. Fix any issues discovered

**Files:** `tests/integration/test_admin_credit_workflows.py`

**Phase 2 Summary:**
- **Total Tasks:** 8 atomic tasks
- **Estimated Time:** 10-15 hours
- **Average Task Size:** 1-3 hours each
- **TDD Approach:** Tests written before implementation for all features

---

### Phase 3: Reporting & Optimization
**Estimated Time:** 8-12 hours
**TDD Approach:** Write failing tests first, then implement code to pass tests

#### Task 3.1: Credit Cache Service (2-3 hours)
**Commit:** `test: add failing tests for credit cache service`
**Commit:** `feat: implement credit balance caching`

**TDD Steps:**
1. Create `tests/test_credit_cache.py` with failing tests:
   - Test cache miss on first read
   - Test cache hit on subsequent read
   - Test cache expiry after TTL
   - Test cache invalidation
   - Test concurrent access
2. Run tests (should fail)
3. Create `src/services/credit_cache.py`
4. Implement cache with 5-minute TTL
5. Run tests (should pass)

**Files:** `tests/test_credit_cache.py`, `src/services/credit_cache.py`

#### Task 3.2: Integrate Cache into Credit Service (1-2 hours)
**Commit:** `test: add failing tests for cache integration`
**Commit:** `feat: integrate caching into credit service`

**TDD Steps:**
1. Add to `tests/test_credit_service.py`:
   - Test `get_customer_credit_balance()` uses cache
   - Test cache invalidation on write operations
   - Test cache pre-warming for batch processing
2. Run tests (should fail)
3. Modify `src/services/credit_service.py` to use cache
4. Add cache invalidation to all write methods
5. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `src/services/credit_service.py`

#### Task 3.3: Credit Export Command (2-3 hours)
**Commit:** `test: add failing tests for /export_credits command`
**Commit:** `feat: add /export_credits command for admins`

**TDD Steps:**
1. Add to `tests/test_admin_credit_commands.py`:
   - Test `/export_credits` generates CSV
   - Test CSV contains 8 required fields
   - Test CSV formatting and encoding
   - Test empty results
2. Run tests (should fail)
3. Implement `/export_credits` in `src/handlers/admin/credit_commands.py`
4. Add to command router and admin panel
5. Run tests (should pass)

**Files:** `tests/test_admin_credit_commands.py`, `src/handlers/admin/credit_commands.py`

#### Task 3.4: Credit Metrics and Monitoring (1-2 hours)
**Commit:** `test: add failing tests for credit metrics`
**Commit:** `feat: add credit system metrics and monitoring`

**TDD Steps:**
1. Create `tests/test_credit_metrics.py` with failing tests:
   - Test CloudWatch metrics are published
   - Test metric values are correct
   - Test cache hit rate calculation
2. Run tests (should fail)
3. Add metrics to `src/services/credit_service.py` and `src/services/credit_cache.py`
4. Run tests (should pass)

**Files:** `tests/test_credit_metrics.py`, `src/services/credit_service.py`, `src/services/credit_cache.py`

#### Task 3.5: Performance Optimization - Batch Processing (1-2 hours)
**Commit:** `test: add failing tests for batch processing optimization`
**Commit:** `refactor: optimize delivery overview batch processing`

**TDD Steps:**
1. Add to `tests/test_delivery_overview_credit.py`:
   - Test batch pre-loads all customer credits
   - Test batch processing time < 5s for 100 customers
   - Test cache effectiveness during batch
2. Run tests (should fail)
3. Modify `src/handlers/admin/delivery_overview_handler.py`
4. Add cache pre-warming
5. Run tests (should pass)

**Files:** `tests/test_delivery_overview_credit.py`, `src/handlers/admin/delivery_overview_handler.py`

#### Task 3.6: Cache Tests (1-2 hours)
**Commit:** `test: add comprehensive cache tests`

**TDD Steps:**
1. Expand `tests/test_credit_cache.py`:
   - Test cache hit/miss scenarios
   - Test cache expiry (TTL)
   - Test cache invalidation on all write operations
   - Test concurrent access patterns
   - Test cache pre-warming
2. Run tests
3. Fix any issues discovered
4. Verify cache hit rate > 80% in batch scenarios

**Files:** `tests/test_credit_cache.py`

#### Task 3.7: Performance Benchmarks (1 hour)
**Commit:** `test: add performance benchmarks for credit operations`

**TDD Steps:**
1. Create `tests/benchmarks/test_credit_performance.py`:
   - Benchmark credit balance queries (target: <100ms)
   - Benchmark credit processing (target: <2s)
   - Benchmark batch processing (target: <5s for 100 customers)
   - Document results
2. Run benchmarks
3. Verify all targets met
4. Document performance characteristics

**Files:** `tests/benchmarks/test_credit_performance.py`

**Phase 3 Summary:**
- **Total Tasks:** 7 atomic tasks
- **Estimated Time:** 8-12 hours
- **Average Task Size:** 1-3 hours each
- **TDD Approach:** Tests written before implementation, includes performance benchmarks

---

### Phase 4: Polish & Edge Cases
**Estimated Time:** 5-8 hours
**TDD Approach:** Write failing tests first, then implement code to pass tests

#### Task 4.1: Guest User Credit Handling (1-2 hours)
**Commit:** `test: add failing tests for guest user credit support`
**Commit:** `feat: add guest user credit support`

**TDD Steps:**
1. Add to `tests/test_delivery_overview_credit.py`:
   - Test guest user delivery overview shows credit info
   - Test credit balance in admin message for guests
   - Test guest flag in credit export
2. Run tests (should fail)
3. Modify `src/handlers/admin/delivery_overview_handler.py`
4. Run tests (should pass)

**Files:** `tests/test_delivery_overview_credit.py`, `src/handlers/admin/delivery_overview_handler.py`

#### Task 4.2: Negative Balance Safeguards (1-2 hours)
**Commit:** `test: add failing tests for negative balance warnings`
**Commit:** `feat: add negative balance warnings and confirmations`

**TDD Steps:**
1. Add to `tests/test_credit_service.py` and `tests/test_admin_credit_commands.py`:
   - Test warning when adjustment creates negative balance
   - Test explicit confirmation required
   - Test reason field mandatory for negative balance
   - Test validation and error messages
2. Run tests (should fail)
3. Add validation to `src/services/credit_service.py`
4. Add confirmation dialog to `src/handlers/admin/credit_commands.py`
5. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `tests/test_admin_credit_commands.py`, `src/services/credit_service.py`, `src/handlers/admin/credit_commands.py`

#### Task 4.3: Concurrent Update Handling (1-2 hours)
**Commit:** `test: add failing tests for concurrent update handling`
**Commit:** `feat: add retry logic for concurrent credit updates`

**TDD Steps:**
1. Add to `tests/test_credit_service.py`:
   - Test exponential backoff for DynamoDB conditional updates
   - Test retry logic on concurrent update conflicts
   - Test max retry limit
   - Test logging for retry attempts
2. Run tests (should fail)
3. Implement retry logic in `src/services/credit_service.py`
4. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `src/services/credit_service.py`

#### Task 4.4: Error Recovery Mechanisms (1 hour)
**Commit:** `test: add failing tests for error recovery`
**Commit:** `feat: add error recovery for credit operations`

**TDD Steps:**
1. Add to `tests/test_credit_service.py` and `tests/test_delivery_overview_credit.py`:
   - Test error handling for failed credit applications
   - Test admin notification for credit failures
   - Test manual resolution workflow
2. Run tests (should fail)
3. Add error handling to `src/services/credit_service.py`
4. Add admin notifications to `src/handlers/admin/delivery_overview_handler.py`
5. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `tests/test_delivery_overview_credit.py`, `src/services/credit_service.py`, `src/handlers/admin/delivery_overview_handler.py`

#### Task 4.5: Enhanced Customer Notifications (1 hour)
**Commit:** `test: add failing tests for enhanced notifications`
**Commit:** `feat: enhance customer credit notifications`

**TDD Steps:**
1. Add to `tests/test_credit_service.py`:
   - Test notification message formatting
   - Test context-specific messages (issued, applied, adjusted)
   - Test helpful tips and contact info
   - Test notification delivery
2. Run tests (should fail)
3. Improve notification logic in `src/services/credit_service.py`
4. Update translation keys
5. Run tests (should pass)

**Files:** `tests/test_credit_service.py`, `src/services/credit_service.py`, `src/translations/en.json`, `src/translations/nl.json`

#### Task 4.6: Edge Case Tests (1-2 hours)
**Commit:** `test: add comprehensive edge case tests for credit system`

**TDD Steps:**
1. Create `tests/test_credit_edge_cases.py`:
   - Test wrong customer credit issuance and correction
   - Test failed delivery with applied credit
   - Test customer deletion with credit balance
   - Test zero and negative amounts
   - Test concurrent operations
   - Test boundary conditions
2. Run tests
3. Fix any issues discovered
4. Verify 80% test coverage achieved

**Files:** `tests/test_credit_edge_cases.py`

#### Task 4.7: Documentation Updates (1 hour)
**Commit:** `docs: update credit system documentation`

- Add admin documentation (how to issue, adjust, view credits)
- Add customer documentation (how credits work)
- Add developer documentation (API, caching, testing)
- Add troubleshooting guide

**Files:** `README.md`, `docs/credit-system-admin-guide.md`, `docs/credit-system-dev-guide.md`
**Note:** Documentation - no tests needed

**Phase 4 Summary:**
- **Total Tasks:** 7 atomic tasks
- **Estimated Time:** 5-8 hours
- **Average Task Size:** 1-2 hours each
- **TDD Approach:** Tests written before implementation for all edge cases

---

**Total Implementation:**
- **Total Tasks:** 36 atomic tasks across 4 phases
- **Total Estimated Time:** 40-57 hours
- **Average Task Size:** 1-3 hours each
- **Smallest Task:** 1 hour (translation keys, documentation)
- **Largest Task:** 4 hours (delivery overview integration)

**TDD Benefits:**
1. **Quality assurance** - Tests define expected behavior before implementation
2. **Regression prevention** - Comprehensive test suite catches breaking changes
3. **Design improvement** - Writing tests first leads to better API design
4. **Documentation** - Tests serve as executable documentation
5. **Confidence** - 80% test coverage ensures system reliability
6. **Refactoring safety** - Can refactor with confidence tests will catch issues

**Commit Pattern:**
- Most tasks have 2 commits: `test:` followed by `feat:` or `refactor:`
- Infrastructure and documentation tasks have single commits
- Integration test tasks focus on comprehensive test coverage

**Benefits of Atomic Task Breakdown:**
1. **Smaller commits** - Each task is focused and reviewable
2. **Incremental progress** - Can stop/resume at any task boundary
3. **Easier testing** - Test each component independently
4. **Clearer history** - Git history shows logical progression
5. **Reduced risk** - Smaller changes = easier to debug/rollback
6. **Better estimation** - Granular tasks improve time estimates
7. **Flexible scheduling** - Can fit 1-3 hour tasks into available time slots
8. **TDD compliance** - Follows Q39 requirement for test-driven development

## Success Criteria

### Functional Requirements
- ✅ Admin can issue credits via command
- ✅ Credits create customer credit balance
- ✅ Credits automatically apply to deliveries
- ✅ Credits carry forward across multiple deliveries
- ✅ Customers can view their credit balance
- ✅ Admin can view and adjust customer credits
- ✅ All transactions are logged and auditable

### Non-Functional Requirements
- ✅ Credit balance queries < 100ms (with cache)
- ✅ Credit processing < 2 seconds
- ✅ Delivery overview generation < 5 seconds for 100 customers
- ✅ Zero credit balance inconsistencies (strong consistency)
- ✅ Complete audit trail for all credit operations

### User Experience
- ✅ Clear credit information in delivery overviews
- ✅ Immediate credit notifications to customers
- ✅ Simple admin workflow for issuing credit
- ✅ Transparent credit balance display

## Risks & Mitigation

| Risk                             | Impact | Probability | Mitigation                                        |
|----------------------------------|--------|-------------|---------------------------------------------------|
| Credit balance inconsistency     | High | Low | Conditional DynamoDB updates, transaction logging |
| Credit application failure       | Medium | Low | Admin notification, manual resolution, audit trail |
| Concurrent credit application    | High | Low | Idempotent operations, transaction deduplication  |
| Cache invalidation failure       | Medium | Low | Short TTL, invalidate on all writes               |
| Customer confusion about credits | Medium | Medium | Clear messaging, immediate notifications          |
| Credit abuse                     | Medium | Low | Admin-only credits, audit trail                   |
| Performance degradation          | Low | Low | Caching, batch optimization                       |
| Data loss during migration       | High | Low | No migration needed (new tables)                  |

## Rollback Plan

**If critical issues discovered:**
1. Disable credit commands (remove from command router)
2. Existing credits remain in database (no data loss)
3. Manual credit application by admin if needed
4. Fix issues and redeploy
5. Re-enable commands

**No data migration required for rollback** - Credit tables are additive, don't affect existing functionality.

## Dependencies

### External Services
- DynamoDB (new tables)
- No additional AWS services required

### Internal Dependencies
- Delivery overview handler (modification)
- Order commands (display enhancement)
- Command router (new commands)
- Translation files (new keys)

### Infrastructure Changes
- CloudFormation template update (2 new tables)
- IAM permissions for new tables
- No API changes

## Documentation Requirements

### Admin Documentation
1. How to issue credits
2. How to view customer credits
3. How to adjust credit balances
4. Credit transaction types explained
5. Troubleshooting guide

### Customer Documentation
1. How credits work
2. How to view credit balance
3. How credits are applied to deliveries
4. Credit policy

### Developer Documentation
1. Credit service API
2. Database schema
3. Caching strategy
4. Transaction types and flows
5. Testing guide

## Appendix: Translation Keys Required

**Admin Keys:**
- `credit_issued_success`
- `credit_confirmation`
- `credit_balance_display`
- `credit_adjustment_success`
- `list_credits_header`
- `credit_transaction_history`

**Customer Keys:**
- `credit_notification`
- `credit_balance_info`
- `credit_applied_notification`
- `delivery_overview_with_credit`
- `no_payment_needed`

**Error Keys:**
- `credit_amount_invalid`
- `credit_exceeds_order_total`
- `customer_not_found_credit`
- `order_not_found_credit`
- `credit_balance_negative`

**Estimated:** 30-40 new translation keys (English + Dutch)

---

## All Questions Resolved

All open questions have been answered and documented in the "Confirmed Decisions" section above. The specification is now complete and ready for implementation.
