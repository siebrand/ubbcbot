# Delivered Box Availability Specification

## Problem Statement

Currently, offer availability and sold-out status are calculated based on order counts. However, customers can delete their completed orders using `/delete_completed`, which causes:

1. **Incorrect availability calculations** - Deleted orders make it appear that space is available when boxes are actually full
2. **Incorrect sold-out status** - Offers show as having availability when all delivered boxes are actually full
3. **Incorrect order status** - New orders placed into delivered boxes should immediately get `ready_for_labeling` status since the wholesale delivery has already occurred

## Solution Overview

Change the availability calculation to be based on **delivered box capacity** rather than order counts. Once boxes are marked as `delivered`, their available space becomes the source of truth for offer availability.

## Key Principles

1. **Delivered boxes are the source of truth** - Once a box status is `delivered`, its `current_quantity` field represents actual filled capacity, regardless of whether order records exist
2. **Orders in delivered boxes start as ready_for_labeling** - Since the wholesale delivery already happened, new orders can skip the `pending` status
3. **Sold-out when all delivered boxes are full** - An offer is sold out when all delivered boxes have `current_quantity >= max_capacity`

## Data Model Changes

### No schema changes required
All necessary fields already exist:
- `Box.status` - Already has `delivered` status
- `Box.current_quantity` - Already tracks filled capacity
- `Box.max_capacity` - Already defines box size
- `Order.status` - Already has `ready_for_labeling` status

## Business Logic Changes

### 1. Availability Calculation

**Current Logic (in `customer/order_commands.py`):**
```python
# Lines 235-245: Calculates availability from all boxes regardless of status
for box in boxes:
    if box.current_quantity < box.max_capacity:
        total_available += box.max_capacity - box.current_quantity
```

**New Logic Required:**
```python
# Only count availability from delivered boxes
delivered_boxes = [box for box in boxes if box.status == BoxStatus.DELIVERED.value]
for box in delivered_boxes:
    if box.current_quantity < box.max_capacity:
        total_available += box.max_capacity - box.current_quantity
```

**Files to modify:**
- `src/handlers/customer/order_commands.py` - `_notify_channel_order()` method (lines 235-245)

### 2. Order Placement Logic

**Current Logic (in `customer/order_commands.py`):**
```python
# Lines 147-152: Finds boxes with OPEN, FULL, or ORDERED status
for box in boxes:
    if box.status in [BoxStatus.OPEN.value, BoxStatus.FULL.value, BoxStatus.ORDERED.value]:
        available_space = box.max_capacity - box.current_quantity
        if available_space >= quantity:
            return box
```

**New Logic Required:**
```python
# Prioritize delivered boxes first, then other boxes
delivered_boxes = [box for box in boxes if box.status == BoxStatus.DELIVERED.value]
other_boxes = [box for box in boxes if box.status in [BoxStatus.OPEN.value, BoxStatus.FULL.value, BoxStatus.ORDERED.value]]

# Try delivered boxes first
for box in delivered_boxes:
    available_space = box.max_capacity - box.current_quantity
    if available_space >= quantity:
        return box

# Fall back to other boxes
for box in other_boxes:
    available_space = box.max_capacity - box.current_quantity
    if available_space >= quantity:
        return box
```

**Files to modify:**
- `src/handlers/customer/order_commands.py` - `_find_or_create_box()` method (lines 147-165)

### 3. Order Status Assignment

**Current Logic (in `customer/order_commands.py`):**
```python
# Lines 193-195: Sets status based on box status
final_status = 'ordered' if box.status == BoxStatus.ORDERED.value else 'pending'
self.db.update_order(created_order.order_id, {'box_id': box.box_id, 'status': final_status})
```

**New Logic Required:**
```python
# Set status based on box status
if box.status == BoxStatus.DELIVERED.value:
    final_status = OrderStatus.READY_FOR_LABELING.value
elif box.status == BoxStatus.ORDERED.value:
    final_status = 'ordered'
else:
    final_status = 'pending'
    
self.db.update_order(created_order.order_id, {'box_id': box.box_id, 'status': final_status})
```

**Files to modify:**
- `src/handlers/customer/order_commands.py` - `_create_and_assign_order()` method (lines 193-195)

### 4. Sold-Out Status Calculation

**Current Logic (in `box_status_manager.py`):**
```python
# Lines 68-82: Checks if any box has available space
has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes)
has_available_space = any(box.current_quantity < box.max_capacity for box in boxes)

# Offer is sold out if at least one box is ordered AND no available space exists
if has_ordered_boxes and not has_available_space:
    if offer.status != OfferStatus.SOLD_OUT.value:
        self.db.update_offer(offer_id, {'status': OfferStatus.SOLD_OUT.value})
```

**New Logic Required:**
```python
# Get delivered boxes
delivered_boxes = [box for box in boxes if box.status == BoxStatus.DELIVERED.value]

# Check if there are any delivered boxes
has_delivered_boxes = len(delivered_boxes) > 0

# Check if there's available space in delivered boxes
has_available_space_in_delivered = any(
    box.current_quantity < box.max_capacity for box in delivered_boxes
)

# Offer is sold out if there are delivered boxes AND no available space in them
if has_delivered_boxes and not has_available_space_in_delivered:
    if offer.status != OfferStatus.SOLD_OUT.value:
        self.db.update_offer(offer_id, {'status': OfferStatus.SOLD_OUT.value})
        new_status = OfferStatus.SOLD_OUT.value
# Offer is active if there's available space in delivered boxes
elif has_delivered_boxes and has_available_space_in_delivered:
    if offer.status != OfferStatus.ACTIVE.value:
        self.db.update_offer(offer_id, {'status': OfferStatus.ACTIVE.value})
        new_status = OfferStatus.ACTIVE.value
```

**Files to modify:**
- `src/services/box_status_manager.py` - `update_offer_status_after_change()` method (lines 68-82)

### 5. Box Creation Prevention

**Current Logic (in `customer/order_commands.py`):**
```python
# Lines 154-165: Creates new box if no ordered boxes exist
has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes) if boxes else False

if offer.status == OfferStatus.ACTIVE.value and not has_ordered_boxes:
    new_box = Box(offer_id=offer_id, max_capacity=offer.wholesale_box_size)
    suitable_box = self.db.create_box(new_box)
```

**New Logic Required:**
```python
# Check if there are any delivered boxes with space
delivered_boxes = [box for box in boxes if box.status == BoxStatus.DELIVERED.value]
has_space_in_delivered = any(
    box.current_quantity < box.max_capacity for box in delivered_boxes
)

# Only create new boxes if:
# 1. Offer is active
# 2. No delivered boxes exist OR all delivered boxes are full
# 3. No ordered boxes exist
has_ordered_boxes = any(box.status == BoxStatus.ORDERED.value for box in boxes) if boxes else False

if offer.status == OfferStatus.ACTIVE.value and not has_ordered_boxes and not has_space_in_delivered:
    new_box = Box(offer_id=offer_id, max_capacity=offer.wholesale_box_size)
    suitable_box = self.db.create_box(new_box)
```

**Files to modify:**
- `src/handlers/customer/order_commands.py` - `_find_or_create_box()` method (lines 154-165)

## Edge Cases & Considerations

### 1. Transition Period
**Question:** What happens to existing orders in boxes that get marked as delivered?
**Answer:** They should automatically transition to `ready_for_labeling` status when the box is marked delivered (this is already handled by `wholesaler_delivery.py`)

### 2. Order Cancellation in Delivered Boxes
**Question:** When an order is cancelled in a delivered box, should the box capacity be freed up?
**Answer:** YES - The `box_status_manager.update_box_after_order_cancellation()` already handles this by decrementing `current_quantity`. This means cancelled orders in delivered boxes will free up space for new orders.

### 3. Multiple Delivered Boxes
**Question:** Can an offer have multiple delivered boxes?
**Answer:** YES - This is expected. Orders should fill delivered boxes in the order they were created (first box first).

### 4. Partial Deliveries
**Question:** What happens when a box is delivered with fewer units than ordered?
**Answer:** The `wholesaler_delivery.py` already handles this by updating `current_quantity` to the received amount. Availability calculations will automatically reflect the actual delivered quantity.

### 5. Admin Order Placement
**Question:** Should admin-placed orders follow the same logic?
**Answer:** YES - Admin orders via `/order_for` use the same `execute_order()` method, so they will automatically follow the new logic.

### 6. Offer Status Transitions
**Question:** Can an offer go from SOLD_OUT back to ACTIVE?
**Answer:** YES - If a customer cancels an order in a delivered box, space becomes available and the offer should transition back to ACTIVE. The `box_status_manager.update_offer_status_after_change()` already handles this.

### 7. Box Status Workflow
**Question:** Does this change the box status workflow?
**Answer:** NO - The workflow remains: `open → full → ordered → delivered`. This change only affects how availability is calculated once boxes reach `delivered` status.

## Testing Requirements

### Unit Tests Required

1. **Test availability calculation with delivered boxes**
   - Offer with 1 delivered box (10/12 filled) → should show 2 available
   - Offer with 1 delivered box (12/12 filled) → should show 0 available
   - Offer with 2 delivered boxes (12/12 and 8/12 filled) → should show 4 available
   - Offer with 1 delivered box (12/12) and 1 open box (0/12) → should show 0 available (only count delivered)

2. **Test order placement into delivered boxes**
   - Place order into delivered box with space → order status should be `ready_for_labeling`
   - Place order into open box → order status should be `pending`
   - Place order into ordered box → order status should be `ordered`

3. **Test sold-out status with delivered boxes**
   - All delivered boxes full → offer should be SOLD_OUT
   - At least one delivered box has space → offer should be ACTIVE
   - No delivered boxes exist → offer status unchanged (existing logic)

4. **Test order cancellation in delivered boxes**
   - Cancel order in delivered box → box current_quantity decreases
   - Cancel order in delivered box → offer transitions from SOLD_OUT to ACTIVE

5. **Test box creation prevention**
   - Delivered box with space exists → should not create new box
   - All delivered boxes full, no ordered boxes → should create new box
   - No delivered boxes, no ordered boxes → should create new box

### Integration Tests Required

1. **Full workflow test**
   - Create offer → place orders → mark boxes as ordered → mark boxes as delivered
   - Delete completed orders → verify availability still correct
   - Place new order → verify it goes into delivered box with `ready_for_labeling` status

2. **Transition test**
   - Existing offer with pending orders in open boxes
   - Mark boxes as delivered → verify orders transition to `ready_for_labeling`
   - Place new order → verify it uses delivered box

## Translation Keys Required

No new translation keys required. All existing keys can be reused.

## Migration Strategy

### Phase 1: Code Changes (No Data Migration)
1. Update `box_status_manager.py` - sold-out calculation
2. Update `customer/order_commands.py` - availability calculation, order placement, order status
3. Deploy changes

### Phase 2: Testing
1. Test in test environment with various scenarios
2. Verify existing orders are not affected
3. Verify new orders work correctly

### Phase 3: Production Deployment
1. Deploy to production
2. Monitor for issues
3. No data migration required - changes are purely logic-based

## Files to Modify

1. **`src/services/box_status_manager.py`**
   - Method: `update_offer_status_after_change()` (lines 68-82)
   - Change: Update sold-out calculation to only consider delivered boxes

2. **`src/handlers/customer/order_commands.py`**
   - Method: `_notify_channel_order()` (lines 235-245)
   - Change: Update availability calculation to only count delivered boxes
   
   - Method: `_find_or_create_box()` (lines 147-165)
   - Change: Prioritize delivered boxes and prevent box creation when delivered boxes have space
   
   - Method: `_create_and_assign_order()` (lines 193-195)
   - Change: Set order status to `ready_for_labeling` when placed in delivered box

## Questions for Clarification

1. **Should we show availability from non-delivered boxes in any UI?**
   - Current spec: Only delivered boxes count for availability
   - Alternative: Show "X units available (Y pending delivery)" to indicate future availability

2. **Should admin be notified when an offer transitions from SOLD_OUT to ACTIVE due to cancellation?**
   - Current spec: No notification (silent transition)
   - Alternative: Send admin notification when this happens

3. **Should we prevent customers from deleting completed orders?**
   - Current spec: Allow deletion (which is why we need this fix)
   - Alternative: Prevent deletion of completed orders entirely

4. **Should we add a database index on box.status for performance?**
   - Current spec: No index changes
   - Alternative: Add GSI on box.status for faster queries (may incur AWS costs)

5. **Should we display box status in customer-facing messages?**
   - Current spec: No changes to customer messages
   - Alternative: Show "Available from delivered stock" vs "Available for pre-order"

## Success Criteria

1. ✅ Customers can delete completed orders without affecting availability calculations
2. ✅ Offers correctly show as SOLD_OUT when all delivered boxes are full
3. ✅ Offers correctly show as ACTIVE when delivered boxes have available space
4. ✅ New orders placed into delivered boxes immediately get `ready_for_labeling` status
5. ✅ Order cancellations in delivered boxes correctly free up space
6. ✅ No new boxes are created when delivered boxes have available space
7. ✅ Existing functionality for non-delivered boxes remains unchanged

## Implementation Estimate

- **Code changes:** 2-3 hours
- **Unit tests:** 2-3 hours
- **Integration tests:** 1-2 hours
- **Testing & validation:** 2-3 hours
- **Total:** 7-11 hours

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Incorrect availability shown to customers | High | Comprehensive unit tests for all scenarios |
| Orders placed in wrong boxes | Medium | Integration tests covering full workflow |
| Performance degradation from filtering boxes | Low | Monitor query performance, add index if needed |
| Existing orders affected | High | Ensure changes only affect new order placement logic |

## Rollback Plan

If issues are discovered after deployment:
1. Revert code changes (pure logic changes, no data migration)
2. No data cleanup required
3. Existing orders and boxes remain unchanged
