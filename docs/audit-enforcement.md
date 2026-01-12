# Audit Trail Enforcement

## Overview

The audit trail system is enforced at the database layer to ensure **no order changes can bypass logging**. This document explains how enforcement works and how to use it correctly.

## Enforcement Strategy

**Combination of Option 1 (Database-Level) + Option 5 (Transaction Pattern)**

### 1. Automatic Logging (Database-Level)

All order modifications automatically log to audit trail:

```python
# In database.py
def update_order(self, order_id: str, updates: Dict[str, Any], admin_id: int = 0, reason: str = "") -> bool:
    # Gets old order
    # Updates order
    # Automatically logs price changes and status changes
```

**What's logged automatically:**
- Price changes (`total_price`)
- Status changes (`status`)
- Order creation

**Cannot be bypassed:** All code must use `db.update_order()` or `db.create_order()` which have audit logging built-in.

### 2. Transaction Methods (Explicit Control)

For sensitive operations, use transaction methods that **require** admin_id and reason:

```python
# Cancel order (requires reason)
db.cancel_order_with_audit(order_id, admin_id=<ADMIN_USER_ID>, reason="Customer request")

# Adjust price (requires reason, optional refund link)
db.adjust_order_price_with_audit(order_id, new_price=25.00, admin_id=<ADMIN_USER_ID>, 
                                  reason="2 bottles defective", credit_transaction_id="txn-123")

# Mark as paid
db.mark_order_paid_with_audit(order_id, admin_id=<ADMIN_USER_ID>)
```

**Benefits:**
- Explicit intent (clear what operation is happening)
- Mandatory context (admin_id and reason required)
- Refund linkage (price adjustments can link to credit transactions)

## Usage Guidelines

### ✅ DO: Use transaction methods for sensitive operations

```python
# Order cancellation
db.cancel_order_with_audit(order_id, admin_id, "Customer changed mind")

# Price adjustment with refund
db.adjust_order_price_with_audit(order_id, new_price, admin_id, 
                                  "Defective product", credit_txn_id)

# Payment processing
db.mark_order_paid_with_audit(order_id, admin_id)
```

### ✅ DO: Provide admin_id and reason for regular updates

```python
# Status change with context
db.update_order(order_id, {'status': 'ready_for_labeling'}, 
                admin_id=<ADMIN_USER_ID>, reason="Labeling completed")
```

### ⚠️ ACCEPTABLE: Use update_order without admin_id for non-sensitive changes

```python
# System updates (delivery notifications, etc.)
db.update_order(order_id, {'delivery_notification_sent': True})
# admin_id defaults to 0 (system), no audit log created for non-significant fields
```

### ❌ DON'T: Directly modify DynamoDB tables

```python
# WRONG - bypasses audit logging
db.orders_table.update_item(Key={'order_id': order_id}, ...)
```

### ❌ DON'T: Use update_order for sensitive operations without context

```python
# WRONG - no audit context
db.update_order(order_id, {'status': 'cancelled'})

# RIGHT - use transaction method
db.cancel_order_with_audit(order_id, admin_id, reason)
```

## What Gets Logged

### Automatically Logged Fields

| Field | Event Type | Logged When |
|-------|-----------|-------------|
| `total_price` | PRICE_CHANGED | Value changes |
| `status` | STATUS_CHANGED / PAYMENT_RECEIVED / ORDER_CANCELLED | Value changes |
| Order creation | ORDER_CREATED | Order created |

### Not Logged (Non-Significant)

- `update_date` (automatic timestamp)
- `delivery_notification_sent` (system flag)
- `box_id` (internal reference)
- Other non-sensitive fields

## Migration Guide

### Existing Code Using update_order

**Before:**
```python
db.update_order(order_id, {'status': 'cancelled'})
```

**After:**
```python
db.cancel_order_with_audit(order_id, admin_id=<ADMIN_USER_ID>, reason="Customer request")
```

### Existing Code Using create_order

**Before:**
```python
order = Order(...)
db.create_order(order)
```

**After:**
```python
order = Order(...)
db.create_order(order, admin_id=0)  # 0 = customer action, or use actual admin_id
```

## Verification

### Check if audit logging is working

```python
from services.audit_service import AuditService

# Get order history
audit = AuditService(db)
history = audit.get_order_history("order-abc123")

for event in history:
    print(f"{event.changed_at}: {event.event_type}")
    print(f"  Changed by: {event.changed_by}")
    print(f"  Reason: {event.reason}")
```

### Query customer events

```python
# Get all cancellations for customer
events = audit.get_customer_events("cust-123", "ORDER_CANCELLED", days=90)
print(f"Customer has {len(events)} cancelled orders in last 90 days")
```

## Security Considerations

### What's Protected

✅ All order price changes are logged  
✅ All order status changes are logged  
✅ All order creations are logged  
✅ Admin ID tracked for all changes  
✅ Reason required for sensitive operations  
✅ Refund linkage for price adjustments  

### What's NOT Protected

⚠️ Direct DynamoDB table access (developers can still bypass if they try)  
⚠️ Manual database modifications outside application  
⚠️ AWS Console direct edits  

### Best Practices

1. **Code reviews:** Ensure all order modifications use proper methods
2. **IAM policies:** Restrict direct DynamoDB access to application role only
3. **Monitoring:** Alert on orders_table modifications outside Lambda
4. **Training:** Educate developers on audit requirements

## Cost Impact

**Minimal:** ~€0.001 per order modification
- 1 write to order_history table per significant change
- Most orders have 2-3 audit entries (created, status change, payment)
- 1000 orders/month = ~€0.003/month in audit writes

## Future Enhancements

### Option: DynamoDB Streams (Bulletproof)

For complete enforcement, enable DynamoDB Streams on orders table:

```yaml
# template.yaml
OrdersTable:
  Properties:
    StreamSpecification:
      StreamViewType: NEW_AND_OLD_IMAGES
```

Lambda processes stream → writes to audit log → **impossible to bypass**

**Trade-offs:**
- Additional Lambda function
- Eventual consistency (audit log slightly delayed)
- Harder to add context (admin_id, reason)
- Higher cost (~€0.01/month)

**Recommendation:** Current approach is sufficient. Only implement streams if compliance requires bulletproof audit trail.
