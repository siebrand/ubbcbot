# Command Refactoring Plan

This document outlines the step-by-step refactoring of command names from old to new naming convention. Each step must be completed with a commit before proceeding to the next.

## Overview
- **Current State**: Commands use new names, but method names and references use old names
- **Goal**: Align all method names, references, and callback data with new command names
- **Strategy**: Refactor one command at a time to maintain system stability

## Commands to Refactor

### 1. create_supplier (was add_supplier)
**Files to modify:**
- `src/handlers/admin/supplier_commands.py`
- `src/services/callback_handler.py`
- `src/services/command_router.py`
- `src/services/bot_service.py`
- `src/utils/edit_context.py`

**Test files to check:**
- `tests/test_command_routing.py`
- `tests/test_callback_routing.py`
- `tests/test_help_system.py`
- `tests/test_webhook_callbacks.py`

**Changes:**
1. Rename `handle_add_supplier` → `handle_create_supplier`
2. Update callback handler method calls
3. Update callback data: `add_supplier_start` → `create_supplier_start`
4. Update edit context: `add_supplier_name` → `create_supplier_name`
5. Update test assertions and test data

**Commit message:**
```
refactor: rename add_supplier to create_supplier

- Rename handle_add_supplier → handle_create_supplier
- Update callback handler and edit context references
- Update callback data and edit context keys
- Update tests to reflect new naming
- Align method names with /create_supplier command
```

### 2. update_supplier (was edit_supplier)
**Files to modify:**
- `src/handlers/admin/supplier_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_edit_supplier` → `handle_update_supplier`
2. Update callback handler method calls

**Commit message:**
```
refactor: rename edit_supplier to update_supplier

- Rename handle_edit_supplier → handle_update_supplier
- Update callback handler references
- Align method names with /update_supplier command
```

### 3. list_boxes (was box_status)
**Files to modify:**
- `src/handlers/admin/offer/boxes.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_box_status` → `handle_list_boxes`
2. Update callback handler method calls

**Commit message:**
```
refactor: rename box_status to list_boxes

- Rename handle_box_status → handle_list_boxes
- Update callback handler references
- Align method names with /list_boxes command
```

### 4. create_order_for (was order_for)
**Files to modify:**
- `src/handlers/admin/order/order_placement.py`
- `src/handlers/admin/order_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_order_for` → `handle_create_order_for`
2. Update callback handler method calls
3. Keep related methods with consistent naming

**Commit message:**
```
refactor: rename order_for to create_order_for

- Rename handle_order_for → handle_create_order_for
- Update callback handler references
- Align method names with /create_order_for command
```

### 5. list_pending (was pending_users)
**Files to modify:**
- `src/handlers/admin/user_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_pending_users` → `handle_list_pending`
2. Update callback handler method calls

**Commit message:**
```
refactor: rename pending_users to list_pending

- Rename handle_pending_users → handle_list_pending
- Update callback handler references
- Align method names with /list_pending command
```

### 6. create_guest (was add_guest)
**Files to modify:**
- `src/handlers/admin/user_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_add_guest` → `handle_create_guest`
2. Update callback handler method calls

**Commit message:**
```
refactor: rename add_guest to create_guest

- Rename handle_add_guest → handle_create_guest
- Update callback handler references
- Align method names with /create_guest command
```

### 7. view_discount (was discount_status)
**Files to modify:**
- `src/handlers/admin/discount_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_discount_status` → `handle_view_discount`
2. Update callback handler method calls

**Commit message:**
```
refactor: rename discount_status to view_discount

- Rename handle_discount_status → handle_view_discount
- Update callback handler references
- Align method names with /view_discount command
```

### 8. delete_old_orders (was delete_old)
**Files to modify:**
- `src/handlers/admin/order/order_maintenance.py`
- `src/handlers/admin/order_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_delete_old` → `handle_delete_old_orders`
2. Update callback handler method calls

**Commit message:**
```
refactor: rename delete_old to delete_old_orders

- Rename handle_delete_old → handle_delete_old_orders
- Update callback handler references
- Align method names with /delete_old_orders command
```

### 9. process_wholesale (was order_wholesale)
**Files to modify:**
- `src/handlers/admin/offer/management.py`
- `src/services/callback_handler.py` 
- `src/services/bot_service.py`
- `src/translations/en.json`
- `src/translations/nl.json`

**Changes:**
1. Rename `handle_order_wholesale` → `handle_process_wholesale`
2. Rename `handle_confirm_order_wholesale` → `handle_confirm_process_wholesale`
3. Update callback patterns: `confirm_order_wholesale_` → `confirm_process_wholesale_`
4. Update translation keys: `order_wholesale_boxes` → `process_wholesale_boxes`
5. Update translation keys: `usage_confirm_order_wholesale` → `usage_confirm_process_wholesale`

**Commit message:**
```
refactor: rename order_wholesale to process_wholesale

- Rename handle_order_wholesale → handle_process_wholesale
- Rename handle_confirm_order_wholesale → handle_confirm_process_wholesale  
- Update callback patterns and translation keys
- Align method names with /process_wholesale command
```

### 10. list_user_orders (was user_orders)
**Files to modify:**
- `src/handlers/admin/order_commands.py`
- `src/handlers/admin/order/order_viewing.py`
- `src/services/callback_handler.py`
- `src/utils/edit_context.py`

**Changes:**
1. Rename `handle_user_orders` → `handle_list_user_orders`
2. Update callback handler method calls
3. Update edit context references: `user_orders_input` → `list_user_orders_input`

**Commit message:**
```
refactor: rename user_orders to list_user_orders

- Rename handle_user_orders → handle_list_user_orders
- Update callback handler and edit context references
- Align method names with /list_user_orders command
```

### 11. export_orders (was all_orders)
**Files to modify:**
- `src/handlers/admin/order_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_all_orders` → `handle_export_orders`
2. Update callback handler method calls

**Commit message:**
```
refactor: rename all_orders to export_orders

- Rename handle_all_orders → handle_export_orders
- Update callback handler references
- Align method names with /export_orders command
```

### 12. list_offer_orders (was offer_orders)
**Files to modify:**
- `src/handlers/admin/order_commands.py`
- `src/services/callback_handler.py`

**Changes:**
1. Rename `handle_offer_orders` → `handle_list_offer_orders`
2. Update callback handler method calls
3. Update related methods: `handle_offer_orders_page`, `handle_offer_orders_detail_page`

**Commit message:**
```
refactor: rename offer_orders to list_offer_orders

- Rename handle_offer_orders → handle_list_offer_orders
- Update related pagination methods
- Update callback handler references
- Align method names with /list_offer_orders command
```

## Instructions for Agent

For each refactoring step:

1. **Read the current step** from this document
2. **Make the specified changes** to the listed files
3. **Check and update tests**:
   - Search for old method/command names in `tests/` directory
   - Update test assertions to use new method names
   - Update test data (callback patterns, command examples)
   - Remove old command names from "old commands" rejection tests
4. **Validate the changes**:
   - No syntax errors exist
   - Method calls are updated consistently across src/ and tests/
   - Callback patterns match new method names
   - All grep validation commands return no results
5. **Commit the changes** using the provided commit message
6. **Verify the commit** was successful before proceeding
7. **Move to the next step**

## Validation Commands

After each step, run these commands to verify consistency:

```bash
# Check for remaining old method names in source code
grep -r "handle_add_supplier\|handle_edit_supplier\|handle_box_status\|handle_order_for\|handle_pending_users\|handle_add_guest\|handle_discount_status\|handle_delete_old\|handle_order_wholesale\|handle_user_orders\|handle_all_orders\|handle_offer_orders" src/ --exclude-dir=__pycache__

# Check for remaining old method names in tests
grep -r "handle_add_supplier\|handle_edit_supplier\|handle_box_status\|handle_order_for\|handle_pending_users\|handle_add_guest\|handle_discount_status\|handle_delete_old\|handle_order_wholesale\|handle_user_orders\|handle_all_orders\|handle_offer_orders" tests/ --exclude-dir=__pycache__

# Check for callback pattern consistency  
grep -r "confirm_order_wholesale\|user_orders_input\|add_supplier_name\|add_supplier_start" src/ --exclude-dir=__pycache__

# Check for old callback patterns in tests
grep -r "confirm_order_wholesale\|user_orders_input\|add_supplier_name\|add_supplier_start" tests/ --exclude-dir=__pycache__

# Check translation key consistency
grep -r "order_wholesale_boxes\|usage_confirm_order_wholesale" src/translations/
```

## Success Criteria

Refactoring is complete when:
- [ ] All method names match command names in source code
- [ ] All method names match command names in tests
- [ ] All callback patterns are consistent
- [ ] All translation keys are updated
- [ ] No old naming patterns remain in src/ or tests/
- [ ] All validation grep commands return no results
- [ ] All functionality works as expected

## Rollback Plan

If issues arise during refactoring:
1. Use `git revert <commit-hash>` to undo the problematic commit
2. Fix the issues identified
3. Re-attempt the refactoring step
4. Continue with remaining steps