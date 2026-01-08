# Guest User Feature Testing Guide

## Prerequisites
Deploy the updated code to test environment:
```bash
./deploy.sh test
```

## Test Scenario: Complete Guest User Workflow

### 1. Create Guest Users

**Test Case 1: Minimal guest (name only)**
```
/add_guest Maria
```
Expected: ✅ Guest user added: Maria (GUEST_001)

**Test Case 2: Guest with last name**
```
/add_guest John Doe
```
Expected: ✅ Guest user added: John Doe (GUEST_002)

**Test Case 3: Guest with contact info**
```
/add_guest Jane Smith jane@example.com
```
Expected: ✅ Guest user added: Jane Smith (GUEST_003)
Contact: jane@example.com

**Test Case 4: Guest with phone**
```
/add_guest Bob Johnson 06-12345678
```
Expected: ✅ Guest user added: Bob Johnson (GUEST_004)
Contact: 06-12345678

### 2. View Guest Users

```
/list_guests
```
Expected: Shows all 4 guests with 🎫 indicator, IDs, and contact info

### 3. View in General User List

```
/list_users
```
Expected: Shows all users including guests with 🎫 indicator

### 4. Update Guest Information

**Update guest name:**
```
/update_user GUEST_001 Maria Garcia
```
Expected: Shows edit interface with first/last name options

**Update first name via callback:**
Click "📝 Edit First Name" button, then type:
```
Maria
```

**Update last name via callback:**
Click "📝 Edit Last Name" button, then type:
```
Garcia-Lopez
```

**Direct update commands:**
```
/update_user_first_name <customer_id_from_guest_001> Maria
/update_user_last_name <customer_id_from_guest_001> Garcia
```

### 5. Place Orders for Guests

**First, create a test offer:**
```
/setup_test_data
```

**Then order for guest:**
```
/order_for GUEST_001 1 2
```
Expected: ✅ Order placed for Maria Garcia

**Order with different quantities:**
```
/order_for GUEST_002 1 5
/order_for GUEST_003 2 3
```

### 6. View Guest Orders

```
/user_orders GUEST_001
```
Expected: Shows all orders for Maria Garcia

```
/user_orders GUEST_002
```
Expected: Shows all orders for John Doe

### 7. View All Orders (CSV Export)

```
/all_orders active
```
Expected: CSV file includes guest orders with GUEST_xxx IDs

### 8. Cancel Guest Order

**First, get order ID from /user_orders, then:**
```
/cancel_order <order_id>
```
Expected: Confirmation dialog, then cancellation success

### 9. Test Delivery Workflow with Guests

**Move to wholesale ordering:**
```
/order_wholesale 1
```
Expected: Shows orders including guest orders

**Process delivery:**
```
/wholesale_delivery
```
Expected: Guest orders appear in delivery workflow

**Complete labeling:**
```
/labeling_completed
```
Expected: Guest orders move to labeling completed

**Send delivery overviews:**
```
/send_overviews
```
Expected: Guests appear in customer list (no PM sent to them)

**Mark as paid:**
```
/mark_paid
```
Expected: Guest orders can be marked as paid

### 10. Test Edge Cases

**Invalid guest ID:**
```
/order_for GUEST_999 1 2
```
Expected: ❌ User 'GUEST_999' not found

**Empty name:**
```
/add_guest
```
Expected: Usage message

**Very long name (should truncate):**
```
/add_guest ThisIsAVeryLongFirstNameThatExceedsOneHundredCharactersAndShouldBeTruncatedByTheSystemToPreventDatabaseIssues
```
Expected: Name truncated to 100 chars

### 11. Verify Backward Compatibility

**Check existing users still work:**
```
/list_users
```
Expected: All existing users display correctly (no errors)

**Order for regular user:**
```
/order_for <regular_username> 1 2
```
Expected: Works normally

### 12. Test Help System

```
/help users
```
Expected: Shows /add_guest and /list_guests commands

### 13. Test Admin Panel Integration

```
/admin
```
Navigate: 👥 Users → Should see guest-related options

## Quick Verification Checklist

- [ ] Create guest with minimal info
- [ ] Create guest with full info (name + contact)
- [ ] List guests shows 🎫 indicator
- [ ] List users shows guests with 🎫 indicator
- [ ] Update guest name works
- [ ] Order for guest works
- [ ] View guest orders works
- [ ] Cancel guest order works
- [ ] Guest orders in CSV export
- [ ] Guest orders in delivery workflow
- [ ] Existing users still work
- [ ] Help text shows new commands

## Expected Behavior Summary

✅ **Guest users:**
- Have GUEST_xxx IDs (sequential)
- Show 🎫 emoji in lists
- Can be updated like regular users
- Can have orders placed for them
- Appear in all admin workflows
- Don't receive Telegram notifications

✅ **Existing users:**
- Continue working without issues
- No migration needed
- No errors when loading
