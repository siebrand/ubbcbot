# Remaining Command Refactoring Plan

This document lists ALL remaining method name refactorings needed to align with the new command names from COMMAND_NAMING_ANALYSIS.md.

## Status: 11 commands fully refactored ✅, 1 command partially complete ⚠️, 11 commands remaining ❌

**Note:** create_order_for main command is done but callback helpers need renaming for consistency.

### Already Completed (from FUNCTION_NAME_REFACTORING_PLAN.md) - ⚠️ PARTIALLY VERIFIED
1. ✅ create_supplier (was add_supplier) - VERIFIED: handle_create_supplier exists
2. ✅ update_supplier (was edit_supplier) - VERIFIED: handle_update_supplier exists
3. ✅ list_boxes (was box_status) - VERIFIED: handle_list_boxes exists
4. ⚠️ create_order_for (was order_for) - INCOMPLETE: Main command done, but 4 callback helpers still use old naming:
   - `handle_order_for_user_select` → should be `handle_create_order_for_user_select`
   - `handle_order_for_offer_select` → should be `handle_create_order_for_offer_select`
   - `handle_order_for_quantity_select` → should be `handle_create_order_for_quantity_select`
   - `handle_order_for_other_quantity` → should be `handle_create_order_for_other_quantity`
5. ✅ list_pending (was pending_users) - VERIFIED: handle_list_pending exists
6. ✅ create_guest (was add_guest) - VERIFIED: handle_create_guest exists
7. ✅ view_discount (was discount_status) - VERIFIED: handle_view_discount exists
8. ✅ delete_old_orders (was delete_old) - VERIFIED: handle_delete_old_orders exists
9. ✅ process_wholesale (was order_wholesale) - VERIFIED: handle_process_wholesale exists
10. ✅ list_user_orders (was user_orders) - VERIFIED: handle_list_user_orders exists
11. ✅ export_orders (was all_orders) - VERIFIED: handle_export_orders exists
12. ✅ list_offer_orders (was offer_orders) - VERIFIED: handle_list_offer_orders exists

**Verification Date:** 2025-01-18
**Verification Method:** Checked for absence of old method names and presence of new method definitions in codebase
**Issue Found:** create_order_for callback helpers still use old `order_for_*` naming instead of `create_order_for_*`

---

## Additional Refactoring Needed

### 0. create_order_for callback helpers (MISSED IN ORIGINAL REFACTORING)
**Status:** ⚠️ INCOMPLETE - Main command refactored but callback helpers missed

**Files to modify:**
- `src/handlers/admin/order/order_placement.py` (4 method definitions)
- `src/handlers/admin/order_commands.py` (4 wrapper methods)
- `src/services/bot_service.py` (1 reference)
- `src/services/callback_handler.py` (4 references)

**Changes:**
1. Rename `handle_order_for_user_select` → `handle_create_order_for_user_select`
2. Rename `handle_order_for_offer_select` → `handle_create_order_for_offer_select`
3. Rename `handle_order_for_quantity_select` → `handle_create_order_for_quantity_select`
4. Rename `handle_order_for_other_quantity` → `handle_create_order_for_other_quantity`
5. Update all 13 references across files

**Validation:**
```bash
grep -r "handle_order_for_" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename order_for callback helpers to create_order_for

- Rename handle_order_for_user_select → handle_create_order_for_user_select
- Rename handle_order_for_offer_select → handle_create_order_for_offer_select
- Rename handle_order_for_quantity_select → handle_create_order_for_quantity_select
- Rename handle_order_for_other_quantity → handle_create_order_for_other_quantity
- Update 13 references across handlers and services
- Complete create_order_for refactoring for consistency
```

---

## Remaining Refactorings (11 commands)

### 13. archive_supplier (was retire_supplier)
**Status:** ❌ NOT STARTED - Method name still uses old name (2 occurrences)

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
**Status:** ❌ NOT STARTED - Method name still uses old name (12 occurrences)

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
**Status:** ❌ NOT STARTED - Method name still uses old name (2 occurrences)

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
**Status:** ❌ NOT STARTED - Method name still uses old name (9 occurrences)

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
**Status:** ❌ NOT STARTED - Method name still uses old name (6 occurrences)

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
**Status:** ❌ NOT STARTED - Method name still uses old name (5 occurrences)

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
**Status:** ❌ NOT STARTED - Method name still uses old name (7 occurrences)

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
**Status:** ❌ NOT STARTED - Method name still uses old name (3 occurrences)

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
**Status:** ❌ NOT STARTED - Method name still uses old name (3 occurrences)

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
**Status:** ❌ NOT STARTED - Method is `handle_order`, needs rename to `handle_create_order` (6 occurrences)

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
**Status:** ❌ NOT STARTED - Method is `handle_my_orders`, needs rename to `handle_list_my_orders` (3 occurrences)

**Files to modify:**
- `src/handlers/customer/info_commands.py`
- `src/services/command_router.py`

**Changes:**
1. Rename `handle_my_orders` → `handle_list_my_orders`
2. Update command router method calls
3. Keep `/my_orders` as permanent alias in command_router.py

**Validation:**
```bash
grep -r "handle_my_orders" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename my_orders to list_my_orders (keep /my_orders alias)

- Rename handle_my_orders → handle_list_my_orders
- Update command router references
- Maintain /my_orders as permanent alias for UX
- Align method names with /list_my_orders command
```

---

## Summary

**Completion Status:**
- Fully Complete: 11/12 (92%)
- Partially Complete: 1/12 (create_order_for - main done, helpers missed)
- Not Started: 11/12 remaining commands

**Total Refactoring Progress: 11.5/23 (50%)**

**Next Steps:**
0. **PRIORITY:** Complete create_order_for callback helpers (13 references)
1. Start with simplest refactorings (fewest occurrences): #13, #15, #20, #21, #23
2. Then tackle medium complexity: #18, #17
3. Finally handle complex ones: #19, #16, #14
4. Follow TDD approach: tests first, implementation second, separate commits
5. Test each refactoring in test environment before proceeding

**Estimated Effort:**
- Complete create_order_for helpers: ~30 min
- Simple (2-3 occurrences): ~15 min each × 5 = 1.25 hours
- Medium (5-6 occurrences): ~30 min each × 2 = 1 hour  
- Complex (7-12 occurrences): ~45 min each × 4 = 3 hours
- **Total: ~5.75 hours**_orders" src/ --include="*.py"
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

## Risk Assessment

### 1. Broken Callbacks
*   **Risk:** Medium. Many of these methods are invoked dynamically via the `CallbackHandler` string parsing. Renaming the method without updating all string references (especially in `callback_handler.py` or where `getattr` is used) will cause runtime `AttributeError`s when users click buttons.
*   **Mitigation:**
    *   Thoroughly search for the *exact string name* of the method before renaming.
    *   Review `callback_handler.py` logic carefully for dynamic dispatch (e.g., `getattr(handler, f"handle_{action}")`).
    *   Verify string literals in other files that might reference the method name.

### 2. Import Errors
*   **Risk:** Low. Most of these are instance methods within handler classes, not standalone functions imported elsewhere.
*   **Mitigation:** Run `grep` for the method name across the entire `src/` directory to catch any direct imports or references.

### 3. Test Failures
*   **Risk:** Medium. Tests likely call these handler methods directly.
*   **Mitigation:** Update test files immediately after renaming. Run `pytest` for the specific handler test file to verify.

## TDD Requirements

### 1. Pre-Refactor Verification
Before renaming any method:
1.  Identify the relevant test file (e.g., `tests/test_admin_operations.py` or specific handler tests).
2.  Run the tests to ensure they currently pass.

### 2. Refactor Cycle
1.  **Rename:** Use IDE refactoring tools or careful find/replace to rename the method definition and known call sites.
2.  **Test Update:** Update the test files to use the new method name.
3.  **Run Tests:** Execute the specific test file again.
    *   If tests fail with `AttributeError`, search for missed references in `callback_handler.py`.
    *   If tests fail with logic errors, ensure no arguments were dropped during the rename.

### 3. Post-Refactor Validation
*   Run the "Validation" grep command provided for each item to ensure the old name is completely gone from the codebase (except potentially in changelogs or comments, which should also be updated if confusing).

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
