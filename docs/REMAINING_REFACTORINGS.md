# Remaining Command Refactoring Plan

This document lists ALL remaining method name refactorings needed to align with the new command names from COMMAND_NAMING_ANALYSIS.md.

## Status: 12 commands already refactored, 11 commands remaining

### Already Completed (from FUNCTION_NAME_REFACTORING_PLAN.md)
1. ✅ create_supplier (was add_supplier)
2. ✅ update_supplier (was edit_supplier)
3. ✅ list_boxes (was box_status)
4. ✅ create_order_for (was order_for)
5. ✅ list_pending (was pending_users)
6. ✅ create_guest (was add_guest)
7. ✅ view_discount (was discount_status)
8. ✅ delete_old_orders (was delete_old)
9. ✅ process_wholesale (was order_wholesale)
10. ✅ list_user_orders (was user_orders)
11. ✅ export_orders (was all_orders)
12. ✅ list_offer_orders (was offer_orders)

---

## Remaining Refactorings (11 commands)

### 13. archive_supplier (was retire_supplier)
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/admin/supplier_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_retire_supplier` → `handle_archive_supplier`
2. Update callback handler method calls
3. Update any internal references

**Validation:**
```bash
grep -r "handle_retire_supplier\|retire_supplier" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename retire_supplier to archive_supplier

- Rename handle_retire_supplier → handle_archive_supplier
- Update callback handler references
- Align method names with /archive_supplier command
```

---

### 14. view_offer (was offer_details)
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/customer/info_commands.py`
- `src/handlers/admin/offer/editing.py` (4 references)
- `src/services/bot_service.py` (1 reference)
- `src/services/command_router.py` (2 references)
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_offer_details` → `handle_view_offer`
2. Update all 7 internal calls to the method
3. Update callback handler method calls

**Validation:**
```bash
grep -r "handle_offer_details\|offer_details" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename offer_details to view_offer

- Rename handle_offer_details → handle_view_offer
- Update 7 internal method calls across handlers
- Update callback handler references
- Align method names with /view_offer command
```

---

### 15. create_box (was add_box)
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/admin/offer/boxes.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_add_box` → `handle_create_box`
2. Update callback handler method calls

**Validation:**
```bash
grep -r "handle_add_box\|add_box" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename add_box to create_box

- Rename handle_add_box → handle_create_box
- Update callback handler references
- Align method names with /create_box command
```

---

### 16. process_delivery (was wholesale_delivery)
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/admin/wholesale_delivery_handler.py` (3 references)
- `src/handlers/admin/wholesale_delivery_commands.py` (2 references)
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_wholesale_delivery` → `handle_process_delivery`
2. Update 3 internal self-references in wholesale_delivery_handler.py
3. Update 2 references in wholesale_delivery_commands.py
4. Update callback handler method calls

**Validation:**
```bash
grep -r "handle_wholesale_delivery\|wholesale_delivery" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename wholesale_delivery to process_delivery

- Rename handle_wholesale_delivery → handle_process_delivery
- Update 5 internal method calls across handlers
- Update callback handler references
- Align method names with /process_delivery command
```

---

### 17. process_labeling (was labeling_completed)
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/admin/labeling_completion_handler.py` (2 references)
- `src/handlers/admin/labeling_commands.py` (2 references)
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_labeling_completed` → `handle_process_labeling`
2. Update 2 internal self-references in labeling_completion_handler.py
3. Update 2 references in labeling_commands.py
4. Update callback handler method calls

**Validation:**
```bash
grep -r "handle_labeling_completed\|labeling_completed" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename labeling_completed to process_labeling

- Rename handle_labeling_completed → handle_process_labeling
- Update 4 internal method calls across handlers
- Update callback handler references
- Align method names with /process_labeling command
```

---

### 18. send_delivery_overviews (was send_overviews)
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/admin/order/order_status.py`
- `src/handlers/admin/order_commands.py` (2 references)
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_send_overviews` → `handle_send_delivery_overviews`
2. Update 2 references in order_commands.py
3. Update callback handler method calls

**Validation:**
```bash
grep -r "handle_send_overviews\|send_overviews" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename send_overviews to send_delivery_overviews

- Rename handle_send_overviews → handle_send_delivery_overviews
- Update method calls in order_commands.py
- Update callback handler references
- Align method names with /send_delivery_overviews command
```

---

### 19. process_payment (was mark_paid)
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/admin/order/order_status.py`
- `src/handlers/admin/order_commands.py` (2 references)
- `src/handlers/admin/delivery_overview_handler.py` (1 reference)
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_mark_paid` → `handle_process_payment`
2. Update 3 internal method calls across handlers
3. Update callback handler method calls

**Validation:**
```bash
grep -r "handle_mark_paid\|mark_paid" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename mark_paid to process_payment

- Rename handle_mark_paid → handle_process_payment
- Update 3 internal method calls across handlers
- Update callback handler references
- Align method names with /process_payment command
```

---

### 20. delete_cancelled_orders (was delete_cancelled) - CUSTOMER COMMAND
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/customer/order_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_delete_cancelled` → `handle_delete_cancelled_orders`
2. Update error logging message
3. Update callback handler method calls

**Validation:**
```bash
grep -r "handle_delete_cancelled[^_]" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename delete_cancelled to delete_cancelled_orders

- Rename handle_delete_cancelled → handle_delete_cancelled_orders
- Update error logging references
- Update callback handler references
- Align method names with /delete_cancelled_orders command
```

---

### 21. delete_completed_orders (was delete_completed) - CUSTOMER COMMAND
**Status:** Method name still uses old name

**Files to modify:**
- `src/handlers/customer/order_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_delete_completed` → `handle_delete_completed_orders`
2. Update error logging message
3. Update callback handler method calls

**Validation:**
```bash
grep -r "handle_delete_completed[^_]" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename delete_completed to delete_completed_orders

- Rename handle_delete_completed → handle_delete_completed_orders
- Update error logging references
- Update callback handler references
- Align method names with /delete_completed_orders command
```

---

### 22. create_order (was order) - CUSTOMER COMMAND WITH PERMANENT ALIAS
**Status:** Check if method name needs updating

**Files to check:**
- `src/handlers/customer/order_commands.py`
- `src/services/callback_handler.py`

**Investigation needed:**
```bash
grep -r "handle_order[^_]" src/ --include="*.py"
```

**If method is named `handle_order`:**

**Changes:**
1. Rename `handle_order` → `handle_create_order`
2. Update callback handler method calls
3. Keep `/order` as permanent alias in command_router.py

**Commit message:**
```
refactor: rename order to create_order (keep /order alias)

- Rename handle_order → handle_create_order
- Update callback handler references
- Maintain /order as permanent alias for UX
- Align method names with /create_order command
```

---

### 23. list_my_orders (was my_orders) - CUSTOMER COMMAND WITH PERMANENT ALIAS
**Status:** Check if method name needs updating

**Files to check:**
- `src/handlers/customer/order_commands.py`
- `src/services/callback_handler.py`

**Investigation needed:**
```bash
grep -r "handle_my_orders" src/ --include="*.py"
```

**If method is named `handle_my_orders`:**

**Changes:**
1. Rename `handle_my_orders` → `handle_list_my_orders`
2. Update callback handler method calls
3. Keep `/my_orders` as permanent alias in command_router.py

**Commit message:**
```
refactor: rename my_orders to list_my_orders (keep /my_orders alias)

- Rename handle_my_orders → handle_list_my_orders
- Update callback handler references
- Maintain /my_orders as permanent alias for UX
- Align method names with /list_my_orders command
```

---

## Execution Order

Execute refactorings in this order to minimize conflicts:

### Phase 1: Simple Renames (No Internal References)
1. archive_supplier
2. create_box
3. view_discount (already done)
4. delete_old_orders (already done)

### Phase 2: Commands with Few Internal References
5. send_delivery_overviews (2 references)
6. delete_cancelled_orders (customer command)
7. delete_completed_orders (customer command)
8. create_order (if needed)
9. list_my_orders (if needed)

### Phase 3: Commands with Multiple Internal References
10. view_offer (7 references)
11. process_payment (3 references)
12. process_delivery (5 references)
13. process_labeling (4 references)

---

## Instructions for Agent

For each refactoring:

1. **Run validation command** to confirm old method name exists
2. **Make the specified changes** to all listed files
3. **Search for additional references**:
   ```bash
   grep -r "old_method_name" src/ tests/ --include="*.py"
   ```
4. **Update tests** if they reference the old method name
5. **Run validation command again** to confirm no old references remain
6. **Commit with provided message**
7. **Move to next refactoring**

---

## Final Validation

After all refactorings are complete, run:

```bash
# Check for any remaining old method names
grep -r "handle_retire_supplier\|handle_offer_details\|handle_add_box\|handle_wholesale_delivery\|handle_labeling_completed\|handle_send_overviews\|handle_mark_paid\|handle_delete_cancelled[^_]\|handle_delete_completed[^_]\|handle_order[^_]\|handle_my_orders" src/ --include="*.py"

# Should return no results
```

---

## Summary

- **Total commands renamed:** 23
- **Already refactored:** 12
- **Remaining to refactor:** 11
- **Estimated effort:** 2-3 hours (one commit per command)
- **Risk level:** Low (one command at a time with validation)
