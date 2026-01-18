# Remaining Command Refactoring Plan

This document lists ALL remaining method name refactorings needed to align with the new command names from COMMAND_NAMING_ANALYSIS.md.

**Implementation Order:** Tasks ordered from simplest (fewest occurrences) to most complex.

## Status: 16 commands fully refactored ✅, 7 commands remaining ❌

**Total Progress: 16/23 (70%)**

---

## Testing Instructions

**CRITICAL:** Always run the full test suite before committing changes!

```bash
# Set up test environment (first time only)
python3 -m venv test_env
source test_env/bin/activate
pip install -r tests/requirements.txt

# Run tests before each commit
source test_env/bin/activate
export PYTHONPATH="$(pwd)/src:$PYTHONPATH"

# Run refactoring unit tests
python -m unittest discover -s tests/handlers/admin -p "test_*.py" -v

# Run legacy tests
python tests/run_tests.py

# Run pytest tests
python -m pytest tests/test_command_routing.py tests/test_callback_routing.py tests/test_customer_orders.py tests/test_box_status_manager.py tests/test_box_filtering_helpers.py tests/test_delivered_box_availability.py tests/test_box_deletion_service.py tests/test_mark_paid_pagination.py tests/test_offer_cache.py tests/test_csv_parser.py tests/test_import_handler.py tests/test_credit_service.py tests/test_repositories/ -v

deactivate
```

---

## Tasks in Recommended Implementation Order

### 0. ✅ COMPLETE: create_order_for callback helpers (13 occurrences)
**Status:** ✅ COMPLETE

**Files modified:**
- `src/handlers/admin/order/order_placement.py` (4 method definitions)
- `src/handlers/admin/order_commands.py` (4 wrapper methods)
- `src/services/bot_service.py` (1 reference)
- `src/services/callback_handler.py` (4 references)

**Changes completed:**
1. Renamed `handle_order_for_user_select` → `handle_create_order_for_user_select`
2. Renamed `handle_order_for_offer_select` → `handle_create_order_for_offer_select`
3. Renamed `handle_order_for_quantity_select` → `handle_create_order_for_quantity_select`
4. Renamed `handle_order_for_other_quantity` → `handle_create_order_for_other_quantity`

**Validation:**
```bash
grep -r "handle_order_for_" src/ --include="*.py"
# Returns no results - all references updated
```

---

### 1. ✅ COMPLETE: archive_supplier (2 occurrences)
**Status:** ✅ COMPLETE

**Files modified:**
- `src/handlers/admin/supplier_commands.py`
- `src/services/command_router.py`

**Changes completed:**
1. Renamed `handle_retire_supplier` → `handle_archive_supplier`

**Validation:**
```bash
grep -r "handle_retire_supplier" src/ --include="*.py"
# Returns no results - all references updated
```

---

### 2. ✅ COMPLETE: create_box (2 occurrences)
**Status:** ✅ COMPLETE

**Files modified:**
- `src/handlers/admin/offer/boxes.py`
- `src/services/command_router.py`
- `tests/test_command_routing.py`

**Changes completed:**
1. Renamed `handle_add_box` → `handle_create_box`

**Validation:**
```bash
grep -r "handle_add_box" src/ --include="*.py"
# Returns no results - all references updated
```

---

### 3. ✅ COMPLETE: delete_cancelled_orders (3 occurrences)
**Status:** ✅ COMPLETE

**Files modified:**
- `src/handlers/customer/order_commands.py`
- `src/services/command_router.py`
- `tests/test_command_routing.py`

**Changes completed:**
1. Renamed `handle_delete_cancelled` → `handle_delete_cancelled_orders`

---

### 4. ✅ COMPLETE: delete_completed_orders (3 occurrences)
**Status:** ✅ COMPLETE

**Files modified:**
- `src/handlers/customer/order_commands.py`
- `src/services/command_router.py`
- `tests/test_command_routing.py`

**Changes completed:**
1. Renamed `handle_delete_completed` → `handle_delete_completed_orders`

---

### 5. list_my_orders (3 occurrences)
**Status:** ❌ NOT STARTED - Customer command with permanent alias

**Files to modify:**
- `src/handlers/customer/info_commands.py`
- `src/services/command_router.py`

**Changes:**
1. Rename `handle_my_orders` → `handle_list_my_orders`
2. Keep `/my_orders` as permanent alias

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

### 6. send_delivery_overviews (5 occurrences)
**Status:** ❌ NOT STARTED

**Files to modify:**
- `src/handlers/admin/order/order_status.py`
- `src/handlers/admin/order_commands.py` (2 references)
- `src/services/command_router.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_send_overviews` → `handle_send_delivery_overviews`

**Validation:**
```bash
grep -r "handle_send_overviews" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename send_overviews to send_delivery_overviews

- Rename handle_send_overviews → handle_send_delivery_overviews
- Update 2 internal method calls in order_commands.py
- Update command router and callback handler references
- Align method names with /send_delivery_overviews command
```

---

### 7. create_order (6 occurrences)
**Status:** ❌ NOT STARTED - Customer command with permanent alias

**Files to modify:**
- `src/handlers/customer/order_commands.py`
- `src/services/command_router.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_order` → `handle_create_order`
2. Keep `/order` as permanent alias

**Validation:**
```bash
grep -r "handle_order[^_]" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename order to create_order (keep /order alias)

- Rename handle_order → handle_create_order
- Update command router and callback handler references
- Maintain /order as permanent alias for UX
- Align method names with /create_order command
```

---

### 8. process_labeling (6 occurrences)
**Status:** ❌ NOT STARTED

**Files to modify:**
- `src/handlers/admin/labeling_completion_handler.py` (2 references)
- `src/handlers/admin/labeling_commands.py` (2 references)
- `src/services/command_router.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_labeling_completed` → `handle_process_labeling`

**Validation:**
```bash
grep -r "handle_labeling_completed" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename labeling_completed to process_labeling

- Rename handle_labeling_completed → handle_process_labeling
- Update 4 internal method calls across handlers
- Update command router and callback handler references
- Align method names with /process_labeling command
```

---

### 9. process_payment (7 occurrences)
**Status:** ❌ NOT STARTED

**Files to modify:**
- `src/handlers/admin/order/order_status.py`
- `src/handlers/admin/order_commands.py` (2 references)
- `src/handlers/admin/delivery_overview_handler.py` (1 reference)
- `src/services/command_router.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_mark_paid` → `handle_process_payment`

**Validation:**
```bash
grep -r "handle_mark_paid" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename mark_paid to process_payment

- Rename handle_mark_paid → handle_process_payment
- Update 3 internal method calls across handlers
- Update command router and callback handler references
- Align method names with /process_payment command
```

---

### 10. process_delivery (9 occurrences)
**Status:** ❌ NOT STARTED

**Files to modify:**
- `src/handlers/admin/wholesale_delivery_handler.py` (3 references)
- `src/handlers/admin/wholesale_delivery_commands.py` (2 references)
- `src/services/command_router.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_wholesale_delivery` → `handle_process_delivery`

**Validation:**
```bash
grep -r "handle_wholesale_delivery" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename wholesale_delivery to process_delivery

- Rename handle_wholesale_delivery → handle_process_delivery
- Update 5 internal method calls across handlers
- Update command router and callback handler references
- Align method names with /process_delivery command
```

---

### 11. view_offer (12 occurrences)
**Status:** ❌ NOT STARTED - Most complex

**Files to modify:**
- `src/handlers/customer/info_commands.py`
- `src/handlers/admin/offer/editing.py` (4 references)
- `src/services/bot_service.py` (1 reference)
- `src/services/command_router.py` (2 references)
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_offer_details` → `handle_view_offer`

**Validation:**
```bash
grep -r "handle_offer_details" src/ --include="*.py"
```

**Commit message:**
```
refactor: rename offer_details to view_offer

- Rename handle_offer_details → handle_view_offer
- Update 7 internal method calls across handlers
- Update command router and callback handler references
- Align method names with /view_offer command
```

---

## Already Completed

1. ✅ create_supplier (was add_supplier)
2. ✅ update_supplier (was edit_supplier)
3. ✅ list_boxes (was box_status)
4. ⚠️ create_order_for (was order_for) - Main done, helpers need fixing (see task #0)
5. ✅ list_pending (was pending_users)
6. ✅ create_guest (was add_guest)
7. ✅ view_discount (was discount_status)
8. ✅ delete_old_orders (was delete_old)
9. ✅ process_wholesale (was order_wholesale)
10. ✅ list_user_orders (was user_orders)
11. ✅ export_orders (was all_orders)
12. ✅ list_offer_orders (was offer_orders)

**Verification Date:** 2025-01-18

---

## Implementation Instructions

For each task:

1. **Validate** old method exists: Run validation command
2. **Rename** method definition in primary file
3. **Update** all references in listed files
4. **Search** for any missed references: `grep -r "old_name" src/ tests/`
5. **Test** changes work (existing tests will verify)
6. **Commit** with provided message
7. **Move** to next task

---

## Summary

**Estimated Effort:**
- Task #0 (priority): ~30 min
- Tasks #1-5 (2-3 occurrences): ~15 min each = 1.25 hours
- Tasks #6-8 (5-6 occurrences): ~25 min each = 1.25 hours
- Tasks #9-11 (7-12 occurrences): ~35 min each = 1.75 hours
- **Total: ~5 hours**

**Progress Tracking:**
- Fully Complete: 11/23 (48%)
- Partially Complete: 1/23 (4%)
- Remaining: 11/23 (48%)
