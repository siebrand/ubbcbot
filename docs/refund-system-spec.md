# Customer Refund System Specification

## Problem Statement

Customers may need refunds for various reasons:
- Order cancelled by admin after payment
- Defective/incorrect product delivered
- Customer dissatisfaction
- Partial delivery with no future delivery expected

**Key Challenge:** Refund amounts may exceed the customer's next delivery total, requiring a credit/balance system.

## Business Requirements

### Core Functionality
1. Admin can issue refunds to customers
2. Refunds can be partial or full order amounts
3. Refunds create a credit balance for the customer
4. Credit balance is automatically applied to future deliveries
5. Credit balance can exceed next delivery amount (carry forward)
6. Admin can view customer credit balances
7. Admin can manually adjust credit balances
8. Customers can view their credit balance
9. Delivery overviews show credit balance and adjusted payment amount

### Refund Scenarios

**Scenario 1: Simple Refund (Refund < Next Delivery)**
- Customer has €20 credit
- Next delivery total: €50
- Payment required: €30

**Scenario 2: Large Refund (Refund > Next Delivery)**
- Customer has €60 credit
- Next delivery total: €50
- Payment required: €0
- Remaining credit: €10 (carries forward)

**Scenario 3: Multiple Deliveries with Credit**
- Customer has €100 credit
- Delivery 1: €40 → €0 payment, €60 credit remains
- Delivery 2: €35 → €0 payment, €25 credit remains
- Delivery 3: €30 → €0 payment, €0 credit remains (credit depleted)

**Scenario 4: Partial Refund**
- Order total: €50
- Refund: €20 (e.g., 2 out of 5 units defective)
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
    transaction_type: str = ""  # REFUND, ADJUSTMENT, APPLIED, MANUAL_ADD, MANUAL_SUBTRACT
    amount: Decimal = Decimal('0.0')  # Positive for credits, negative for usage
    balance_before: Decimal = Decimal('0.0')
    balance_after: Decimal = Decimal('0.0')
    reference_id: Optional[str] = None  # order_id for refunds, delivery_batch_id for applications
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
    
    # Refund linkage (optional)
    credit_transaction_id: Optional[str] = None  # Links to CreditTransaction if change triggered refund
    triggers_refund: bool = False  # Flag indicating this change caused a refund
    
    # TTL for automatic cleanup (2 years)
    ttl: Optional[int] = None  # Unix timestamp for DynamoDB TTL
```

**Relationship to Refund System:**
- When order price is adjusted → OrderHistory entry created
- If adjustment triggers refund → `credit_transaction_id` links to CreditTransaction
- Provides complete audit trail: "Order price changed from X to Y, refund of Z issued"

### Modified Entities

**Customer** - No changes needed (credit is separate table)

**Order** - Add optional field:
```python
refund_amount: Optional[Decimal] = None  # Amount refunded for this order
refund_reason: Optional[str] = None  # Reason for refund
refunded_at: Optional[datetime] = None  # When refund was issued
```

## Transaction Types

| Type | Description | Amount Sign | Example |
|------|-------------|-------------|---------|
| REFUND | Refund for cancelled/defective order | Positive | +€20.00 |
| ADJUSTMENT | Admin manual adjustment | Positive/Negative | +€5.00 or -€5.00 |
| APPLIED | Credit applied to delivery | Negative | -€30.00 |
| MANUAL_ADD | Admin adds credit | Positive | +€10.00 |
| MANUAL_SUBTRACT | Admin removes credit | Negative | -€10.00 |


## Audit Trail Integration

### Purpose

The Order History table provides a complete audit trail that complements the refund system:
- **Credit Transactions** track money movements (refunds, credits, applications)
- **Order History** tracks data changes (what changed, why, and who changed it)

Together they answer:
- "Why was this refund issued?" → Order History shows price adjustment
- "What refund was issued?" → Credit Transaction shows refund amount
- "Who made the change?" → Both tables track admin_id
- "When did it happen?" → Both tables have timestamps

### Audit Trail Flow

**Example: Defective Product Refund**

1. **Admin adjusts order price** (2 defective bottles out of 5)
   ```python
   # Order updated
   order.total_price: 50.00 → 30.00
   
   # Order History entry created
   OrderHistory(
       order_id="order-abc",
       field_name="total_price",
       old_value="50.00",
       new_value="30.00",
       reason="2 bottles defective",
       changed_by=15005473,
       triggers_refund=True,
       credit_transaction_id="txn-001"
   )
   ```

2. **System issues refund automatically**
   ```python
   # Credit Transaction created
   CreditTransaction(
       transaction_id="txn-001",
       customer_id="cust-123",
       transaction_type="REFUND",
       amount=20.00,
       reference_id="order-abc",
       reason="2 bottles defective",
       created_by=15005473
   )
   ```

3. **Complete audit trail established**
   - Order History: Shows what changed (price 50→30)
   - Credit Transaction: Shows refund issued (€20)
   - Linked via `credit_transaction_id`

### Query Capabilities

**Query 1: "Show complete history for order"**
```python
# Get all changes to order
history = get_order_history(order_id)

# Results:
# - Price changed: 50.00 → 30.00 (refund triggered)
# - Status changed: completed → completed
# - Linked refund: €20.00 (txn-001)
```

**Query 2: "Show all refunds with reasons"**
```python
# Get refund transactions
refunds = get_credit_transactions(type="REFUND")

# For each refund, get order history
for refund in refunds:
    history = get_order_history(refund.reference_id)
    # Shows: What changed that triggered the refund
```

**Query 3: "Show all actions by admin"**
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

**When to log Order History:**
- Price changes (unit_price, total_price)
- Quantity changes
- Status changes (if significant)
- Refund-related fields (refund_amount, refund_reason)

**When NOT to log:**
- Automatic system updates (update_date)
- Non-significant status transitions
- Read operations

**Logging helper:**
```python
def log_order_change_with_refund(order_id, field, old, new, reason, admin_id, refund_amount=None):
    # Create order history entry
    history = OrderHistory(
        order_id=order_id,
        field_name=field,
        old_value=str(old),
        new_value=str(new),
        reason=reason,
        changed_by=admin_id,
        triggers_refund=(refund_amount is not None)
    )
    
    # If refund triggered, create credit transaction
    if refund_amount:
        txn = create_credit_transaction(
            customer_id=get_customer_for_order(order_id),
            transaction_type="REFUND",
            amount=refund_amount,
            reference_id=order_id,
            reason=reason,
            created_by=admin_id
        )
        history.credit_transaction_id = txn.transaction_id
    
    # Save history
    create_order_history(history)
```


## Admin Commands

### 1. Issue Refund

**Command:** `/refund <username_or_order_id> <amount> [reason]`

**Examples:**
```
/refund john_doe 20.50 Defective bottles
/refund a1b2c3d4 15.00 Cancelled order
/refund @johndoe 50.00 Customer dissatisfaction
```

**Workflow:**
1. Admin enters command
2. System validates customer/order exists
3. If order_id provided, show order details for confirmation
4. If username provided, show recent orders to select from (optional)
5. Show confirmation with:
   - Customer name
   - Refund amount
   - Current credit balance
   - New credit balance after refund
   - Reason
6. Admin confirms
7. System creates credit transaction
8. System updates customer credit balance
9. System updates order (if order_id provided)
10. System notifies customer
11. System confirms to admin

**Alternative Flow (Button-based):**
1. Admin uses `/refund` without args
2. System prompts for username input
3. System shows customer's completed/cancelled orders
4. Admin selects order
5. System shows refund options:
   - Full refund (order total)
   - Partial refund (enter amount)
   - Custom amount (not tied to order)
6. Admin enters reason
7. Confirmation and execution as above

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
• 2024-01-10: +€20.00 (REFUND) - Defective bottles [Order: a1b2c3d4]
• 2024-01-08: -€30.00 (APPLIED) - Applied to delivery
• 2024-01-05: +€25.50 (REFUND) - Cancelled order [Order: e5f6g7h8]

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
• 2024-01-10: +€20.00 - Refund for order #a1b2c3d4
• 2024-01-05: +€25.50 - Refund for order #e5f6g7h8

Recent Usage:
• 2024-01-08: -€30.00 - Applied to delivery

Questions? Contact admin.
```

### 2. View Orders with Refunds

**Command:** `/my_orders` (enhanced to show refunds)

**Output Enhancement:**
```
📦 Your Orders

Active Orders:
• [2024-01-12] 3x Brewery IPA - €30.00 (pending)

Completed Orders:
• [2024-01-10] 2x Stout Beer - €20.00 (completed)
  ↳ ⚠️ Refunded: €20.00 - Defective bottles

Cancelled Orders:
• [2024-01-05] 5x Lager - €25.50 (cancelled)
  ↳ 💰 Refunded: €25.50 - Order cancelled by admin
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

### Credit Application Rules

1. **Automatic Application**
   - Credits are ALWAYS automatically applied during delivery overview generation
   - No manual customer action required
   - Credits applied in chronological order (oldest first)

2. **Credit Limits**
   - No maximum credit balance limit
   - Credits never expire
   - Credits are non-transferable between customers

3. **Refund Limits**
   - Refund amount cannot exceed original order total
   - Partial refunds allowed (e.g., refund 2 out of 5 units)
   - Multiple refunds per order not allowed (one refund per order maximum)

4. **Credit Usage Priority**
   - Credits applied before any payment
   - If multiple credit sources exist, use oldest first (FIFO)
   - Credit application is atomic (all or nothing per delivery)

5. **Order Status and Refunds**
   - Can refund: COMPLETED, CANCELLED, AWAITING_PAYMENT orders
   - Cannot refund: PENDING, ORDERED, READY_FOR_LABELING orders (cancel instead)
   - Refunded orders remain in database with refund metadata

### Calculation Logic

**Credit Application Algorithm:**
```python
def apply_credit_to_delivery(customer_id: str, delivery_total: Decimal) -> Dict:
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

## Edge Cases & Considerations

### 1. Refund After Credit Already Applied
**Scenario:** Customer receives delivery, pays €30 (after €20 credit applied). Later, admin issues €50 refund for defective items.

**Question:** Should the refund be:
- A) €50 credit (full refund amount)
- B) €30 credit (only what customer actually paid)
- C) €50 credit, but note that €20 was already credited

**Recommendation:** Option A - Full refund amount as credit. The original credit and new refund are separate transactions.

### 2. Refund for Guest Users
**Question:** Can guest users receive refunds?

**Considerations:**
- Guest users don't have Telegram accounts
- Credits cannot be applied automatically
- Need alternative refund method (cash, bank transfer)

**Recommendation:** 
- Allow credit balance for guest users
- Admin manually tracks when guest credit is settled
- Add "settled" flag to credit transactions for guests

### 3. Customer Deletion with Credit Balance
**Question:** What happens if customer is deleted/rejected with remaining credit?

**Options:**
- A) Prevent deletion if credit balance > 0
- B) Transfer credit to admin notification for manual settlement
- C) Allow deletion, credit is forfeited

**Recommendation:** Option A - Prevent deletion, require credit settlement first.

### 4. Concurrent Credit Application
**Question:** What if two deliveries are processed simultaneously?

**Mitigation:** Use DynamoDB conditional updates to ensure atomic credit balance updates.

### 5. Refund Larger Than Order Total
**Question:** Should admin be able to issue refund > order total?

**Options:**
- A) Block refunds > order total
- B) Allow with warning
- C) Allow freely (for goodwill gestures)

**Recommendation:** Option B - Allow with explicit warning and confirmation.

### 6. Credit Display in Order History
**Question:** Should order history show original price or price after credit?

**Recommendation:** Show both:
- Original order total
- Credit applied (if any)
- Amount paid

### 7. Partial Delivery with Refund
**Scenario:** Order 10 units, receive 6 units, 4 units cancelled.

**Question:** Should refund be automatic or manual?

**Options:**
- A) Automatic refund for undelivered units
- B) Manual admin refund decision
- C) Automatic credit, admin can adjust

**Recommendation:** Option B - Manual decision. Admin may want to offer discount on future order instead.

### 8. Refund Notification Timing
**Question:** When should customer be notified of refund?

**Options:**
- A) Immediately when refund issued
- B) With next delivery overview
- C) Both

**Recommendation:** Option A - Immediate notification for transparency.

### 9. Credit Balance in Order Placement
**Question:** Should customers see credit balance when placing orders?

**Recommendation:** No - Credits only apply at delivery/payment time, not at order time.

### 10. Negative Credit Balance
**Question:** Can credit balance go negative (customer owes money)?

**Options:**
- A) Never allow negative balance
- B) Allow for corrections (e.g., overpayment refund reversal)

**Recommendation:** Option A - Use separate debt tracking if needed.


## Implementation Details

### Files to Create

1. **`src/models/entities.py`** - Add new dataclasses:
   - `CustomerCredit`
   - `CreditTransaction`
   - `OrderHistory`
   - Add refund fields to `Order`

2. **`src/services/credit_service.py`** - New service:
   - `get_customer_credit_balance(customer_id)`
   - `create_credit_transaction(transaction_data)`
   - `apply_credit_to_delivery(customer_id, delivery_total)`
   - `issue_refund(customer_id, amount, reason, order_id, admin_id)`
   - `adjust_credit_balance(customer_id, amount, reason, admin_id)`
   - `get_credit_transactions(customer_id, limit, days)`
   - `get_customers_with_credit(min_amount)`

3. **`src/services/audit_service.py`** - New service:
   - `log_order_change(order_id, admin_id, field_name, old_value, new_value, reason, credit_transaction_id)`
   - `get_order_history(order_id, limit)`
   - `get_changes_by_admin(admin_id, days)`

4. **`src/handlers/admin/credit_commands.py`** - New handler:
   - `handle_refund(chat_id, args)`
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
   - `handle_my_orders()` - Show refund information

4. **`src/services/command_router.py`** - Add new commands:
   - `/refund` → admin credit handler
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
   - Refund notifications
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

Add new section: **💰 Credits & Refunds**

Buttons:
- Issue Refund
- View Credit Balances
- Adjust Credit
- Credit History
- Export Credits Report

### Notification Messages

**Customer Refund Notification:**
```
💰 Refund Issued

You have received a refund of €20.00

Reason: Defective bottles
Order: #a1b2c3d4 - 2x Stout Beer

Your new credit balance: €45.50

This credit will be automatically applied to your next delivery.

Questions? Contact admin.
```

**Customer Credit Applied Notification:**
```
💰 Credit Applied

Your credit of €20.00 has been applied to your delivery.

Original Total: €50.00
Credit Applied: -€20.00
Amount to Pay: €30.00

Remaining Credit: €0.00
```

**Admin Refund Confirmation:**
```
✅ Refund Issued Successfully

Customer: John Doe (@johndoe)
Amount: €20.00
Reason: Defective bottles
Order: #a1b2c3d4

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
   - Test refund issuance
   - Test credit adjustment
   - Test concurrent credit updates

2. **Credit Calculation Tests**
   - Credit < delivery total
   - Credit > delivery total
   - Credit = delivery total
   - Zero credit
   - Multiple credits applied

3. **Refund Validation Tests**
   - Refund amount validation
   - Order status validation
   - Duplicate refund prevention
   - Refund > order total handling

### Integration Tests

1. **Full Refund Workflow**
   - Issue refund → verify credit balance → apply to delivery → verify payment

2. **Multi-Delivery Credit Usage**
   - Large refund → multiple deliveries → credit depletion

3. **Guest User Refund**
   - Issue refund to guest → verify credit tracking

4. **Concurrent Operations**
   - Simultaneous credit applications
   - Refund during delivery processing

### Manual Testing Scenarios

1. Issue refund for completed order
2. Issue refund for cancelled order
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
   - Frequency: Medium (admin checking before refund/adjustment)
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

6. **Issue refund** - `/refund` command
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
1. After issuing refund → `CreditCache.invalidate(customer_id)`
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
- Add after core refund functionality works
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
4. Cache invalidation after refund
5. Cache invalidation after credit application
6. Concurrent access (multiple Lambda invocations)


## Critical Questions Requiring Answers

### 1. Refund Policy Questions

**Q1.1:** Can refunds be issued for orders in PENDING or ORDERED status?
- **Option A:** No - Cancel the order instead (no refund needed, order not yet paid)
- **Option B:** Yes - Allow refund for pre-paid orders
- **Recommendation:** Option A - Use cancellation for unpaid orders

**Q1.2:** Should there be a time limit for issuing refunds?
- **Option A:** No time limit (refund anytime)
- **Option B:** 30 days after delivery
- **Option C:** 90 days after delivery
- **Recommendation:** Option A - Admin discretion, no automatic limit

**Q1.3:** Can the same order be refunded multiple times?
- **Option A:** No - One refund per order maximum
- **Option B:** Yes - Allow multiple partial refunds
- **Recommendation:** Option A - Simpler tracking, prevents abuse

**Q1.4:** Should refunds be allowed for orders with status AWAITING_PAYMENT?
- **Option A:** Yes - Customer paid but admin issues refund before marking as paid
- **Option B:** No - Wait until COMPLETED status
- **Recommendation:** Option A - Allows flexibility for payment issues

### 2. Credit Application Questions

**Q2.1:** Should credit application be automatic or require customer consent?
- **Option A:** Automatic (always apply)
- **Option B:** Customer can opt-out
- **Option C:** Customer must opt-in
- **Recommendation:** Option A - Simplest, most expected behavior

**Q2.2:** Can customers request to NOT use their credit for a specific delivery?
- **Option A:** No - Credit always applied automatically
- **Option B:** Yes - Customer can request to save credit
- **Recommendation:** Option A - Simpler implementation, rare use case

**Q2.3:** Should credit be applied to guest user deliveries?
- **Option A:** Yes - Track credit, admin manually settles
- **Option B:** No - Guest users get direct refunds only
- **Recommendation:** Option A - Consistent system, admin flexibility

**Q2.4:** What happens if delivery overview is regenerated for same customer?
- **Option A:** Credit applied again (double application)
- **Option B:** Check if already applied, skip
- **Option C:** Prevent regeneration if credit already applied
- **Recommendation:** Option B - Idempotent operation with transaction tracking

### 3. Notification Questions

**Q3.1:** Should customers be notified immediately when refund is issued?
- **Option A:** Yes - Immediate notification
- **Option B:** No - Only show in next delivery overview
- **Option C:** Both - Immediate + reminder in overview
- **Recommendation:** Option A - Transparency and customer satisfaction

**Q3.2:** Should customers be notified when credit is applied to delivery?
- **Option A:** Yes - Separate notification
- **Option B:** No - Only shown in delivery overview
- **Recommendation:** Option B - Delivery overview already shows credit application

**Q3.3:** Should admin be notified when customer views their credit balance?
- **Option A:** Yes - Track customer awareness
- **Option B:** No - Privacy concern
- **Recommendation:** Option B - Unnecessary tracking

### 4. Reporting Questions

**Q4.1:** Should there be a monthly credit report for accounting?
- **Option A:** Yes - Automated monthly report
- **Option B:** Yes - On-demand report only
- **Option C:** No - Admin queries as needed
- **Recommendation:** Option B - Flexibility without automation overhead

**Q4.2:** What credit metrics should be tracked?
- **Suggested Metrics:**
  - Total outstanding credits
  - Total credits issued this month
  - Total credits applied this month
  - Average credit per customer
  - Customers with credit > €50
- **Recommendation:** Implement basic metrics, expand based on need

**Q4.3:** Should credit transactions be exportable to CSV?
- **Option A:** Yes - Include in `/all_orders` export
- **Option B:** Yes - Separate `/export_credits` command
- **Option C:** No - Admin can query as needed
- **Recommendation:** Option B - Separate export for accounting

### 5. Technical Questions

**Q5.1:** Should credit balance be cached?
- **Answer:** YES - See caching strategy section above
- **Implementation:** In-memory cache with 5-minute TTL

**Q5.2:** How to handle concurrent credit updates?
- **Option A:** DynamoDB conditional updates (optimistic locking)
- **Option B:** Lambda concurrency limit = 1 (pessimistic locking)
- **Option C:** Accept eventual consistency
- **Recommendation:** Option A - Conditional updates with retry logic

**Q5.3:** Should credit transactions be immutable?
- **Option A:** Yes - Never delete/modify transactions (audit trail)
- **Option B:** No - Allow admin to delete erroneous transactions
- **Recommendation:** Option A - Immutable audit trail, use adjustment transactions for corrections

**Q5.4:** What precision for credit amounts?
- **Option A:** 2 decimal places (cents)
- **Option B:** 4 decimal places (for future flexibility)
- **Recommendation:** Option A - Match currency precision (€0.01)

**Q5.5:** Should there be a maximum credit balance per customer?
- **Option A:** No limit
- **Option B:** €500 limit (flag for admin review)
- **Option C:** €1000 limit (hard cap)
- **Recommendation:** Option A - No limit, admin discretion

### 6. Edge Case Questions

**Q6.1:** What if customer is deleted while having credit balance?
- **Option A:** Prevent deletion (require settlement first)
- **Option B:** Transfer credit to admin notification
- **Option C:** Allow deletion, credit forfeited
- **Recommendation:** Option A - Prevent data loss

**Q6.2:** What if refund is issued for wrong customer?
- **Option A:** Admin manually reverses (adjustment transaction)
- **Option B:** System provides "undo refund" feature
- **Recommendation:** Option A - Manual correction with audit trail

**Q6.3:** What if credit is applied but delivery fails?
- **Option A:** Credit remains applied (customer must contact admin)
- **Option B:** Automatic credit restoration
- **Recommendation:** Option A - Manual resolution, rare case

**Q6.4:** Should there be a "credit expiry" feature?
- **Option A:** No - Credits never expire
- **Option B:** Yes - 1 year expiry
- **Option C:** Yes - Configurable expiry
- **Recommendation:** Option A - No expiry, simpler system

## Implementation Phases

### Phase 1: Core Refund System (MVP)
**Estimated Time:** 17-22 hours

**Deliverables:**
1. Database tables (CustomerCredits, CreditTransactions, OrderHistory)
2. Credit service (issue refund, get balance, apply credit)
3. Audit service (log order changes, link to refunds)
4. Admin refund command (basic)
5. Customer credit view command
6. Delivery overview integration (credit application)
7. Basic notifications
8. Order history logging for refund-related changes

**Testing:** Unit tests for credit service, audit service tests, integration test for refund workflow

### Phase 2: Enhanced Admin Features
**Estimated Time:** 10-15 hours

**Deliverables:**
1. Credit adjustment command
2. List customers with credit
3. Credit transaction history
4. Admin panel integration
5. Enhanced refund UI (button-based)

**Testing:** Admin workflow tests, pagination tests

### Phase 3: Reporting & Optimization
**Estimated Time:** 8-12 hours

**Deliverables:**
1. Credit caching implementation
2. Credit export/reporting
3. Metrics and monitoring
4. Performance optimization

**Testing:** Cache tests, performance benchmarks, load testing

### Phase 4: Polish & Edge Cases
**Estimated Time:** 5-8 hours

**Deliverables:**
1. Guest user credit handling
2. Concurrent update handling
3. Error recovery mechanisms
4. Enhanced customer notifications
5. Documentation updates

**Testing:** Edge case tests, concurrent operation tests

**Total Estimated Time:** 40-57 hours

## Success Criteria

### Functional Requirements
- ✅ Admin can issue refunds via command
- ✅ Refunds create customer credit balance
- ✅ Credits automatically apply to deliveries
- ✅ Credits carry forward across multiple deliveries
- ✅ Customers can view their credit balance
- ✅ Admin can view and adjust customer credits
- ✅ All transactions are logged and auditable
- ✅ Complete order change history with refund linkage

### Non-Functional Requirements
- ✅ Credit balance queries < 100ms (with cache)
- ✅ Refund processing < 2 seconds
- ✅ Delivery overview generation < 5 seconds for 100 customers
- ✅ Zero credit balance inconsistencies (strong consistency)
- ✅ Complete audit trail for all credit operations

### User Experience
- ✅ Clear credit information in delivery overviews
- ✅ Immediate refund notifications to customers
- ✅ Simple admin workflow for issuing refunds
- ✅ Transparent credit balance display

## Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Credit balance inconsistency | High | Low | Conditional DynamoDB updates, transaction logging |
| Concurrent credit application | High | Low | Idempotent operations, transaction deduplication |
| Cache invalidation failure | Medium | Low | Short TTL, invalidate on all writes |
| Customer confusion about credits | Medium | Medium | Clear messaging, immediate notifications |
| Refund abuse | Medium | Low | Admin-only refunds, audit trail |
| Performance degradation | Low | Low | Caching, batch optimization |
| Data loss during migration | High | Low | No migration needed (new tables) |

## Rollback Plan

**If critical issues discovered:**
1. Disable refund commands (remove from command router)
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
1. How to issue refunds
2. How to view customer credits
3. How to adjust credit balances
4. Credit transaction types explained
5. Troubleshooting guide

### Customer Documentation
1. How credits work
2. How to view credit balance
3. How credits are applied to deliveries
4. Refund policy

### Developer Documentation
1. Credit service API
2. Database schema
3. Caching strategy
4. Transaction types and flows
5. Testing guide

## Appendix: Translation Keys Required

**Admin Keys:**
- `refund_issued_success`
- `refund_confirmation`
- `credit_balance_display`
- `credit_adjustment_success`
- `list_credits_header`
- `credit_transaction_history`

**Customer Keys:**
- `refund_notification`
- `credit_balance_info`
- `credit_applied_notification`
- `delivery_overview_with_credit`
- `no_payment_needed`

**Error Keys:**
- `refund_amount_invalid`
- `refund_exceeds_order_total`
- `customer_not_found_refund`
- `order_not_found_refund`
- `credit_balance_negative`

**Estimated:** 30-40 new translation keys (English + Dutch)
