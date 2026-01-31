# Command Naming Analysis & Overhaul Plan

## Executive Summary

This document provides a comprehensive analysis of all 90+ commands in the UBBC Bot system and proposes a standardized naming convention to improve consistency, discoverability, and usability.

## Current State Analysis

### Identified Issues

1. **Inconsistent Action Verbs**: Mix of `add_`, `create_`, `update_`, `edit_`
2. **Unclear Hierarchy**: No clear pattern for related commands
3. **Redundant Naming**: Some commands have overlapping purposes
4. **Mixed Patterns**: Some use `action_object`, others use `object_action`
5. **Callback vs Command Confusion**: Internal callbacks mixed with user commands

---

## Proposed Naming Convention

### Core Principles

1. **Action-Object Pattern**: `{action}_{object}` (e.g., `create_offer`, `list_suppliers`)
2. **Consistent Verbs**: Standardize on specific verbs for specific actions
3. **Clear Hierarchy**: Group related commands with common prefixes
4. **User vs Admin**: Clear distinction in naming

### Standard Action Verbs

| Verb | Purpose | Examples |
|------|---------|----------|
| `create_` | Create new entity | `create_offer`, `create_supplier` |
| `view_` | View single entity details | `view_offer`, `view_order` |
| `list_` | View collection/multiple entities | `list_offers`, `list_suppliers` |
| `update_` | Modify entity attributes | `update_offer_price`, `update_user_name` |
| `delete_` | Remove entity permanently | `delete_offer`, `delete_order` |
| `archive_` | Soft delete/retire entity | `archive_supplier`, `archive_offer` |
| `process_` | Multi-step workflow | `process_delivery`, `process_wholesale` |
| `finalize_` | Complete workflow | `finalize_import`, `finalize_delivery` |
| `cancel_` | Abort operation | `cancel_offer`, `cancel_order` |
| `approve_` | Grant permission | `approve_user` |
| `reject_` | Deny permission | `reject_user` |

---

## Detailed Command Mapping

### 1. Core System Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/start` | `/start` | ✅ Standard Telegram convention | Keep |
| `/help` | `/help` | ✅ Universal convention | Keep |
| `/cancel` | `/cancel` | ✅ Clear and standard | Keep |
| `/admin` | `/admin` | ✅ Clear admin entry point | Keep |
| `/changelog` | `/changelog` | ✅ Clear purpose | Keep |

**Rationale**: These commands follow universal conventions and should remain unchanged.

---

### 2. Supplier Management Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/add_supplier` | `/create_supplier` | Consistency with `create_` pattern | High |
| `/retire_supplier` | `/archive_supplier` | "Archive" clearer than "retire" | High |
| `/list_suppliers` | `/list_suppliers` | ✅ Already follows convention | Keep |
| `/edit_supplier` | `/update_supplier` | Consistency with `update_` pattern | Medium |
| `/update_supplier_name` | `/update_supplier_name` | ✅ Already follows convention | Keep |
| `/update_supplier_contact` | `/update_supplier_contact` | ✅ Already follows convention | Keep |
| `/update_supplier_full_name` | `/update_supplier_full_name` | ✅ Already follows convention | Keep |

**Rationale**: 
- `create_` is more intuitive than `add_` for entity creation
- `archive_` better conveys "still exists but inactive" vs `retire_`
- `update_` is clearer than `edit_` for specific field changes

---

### 3. Offer Management Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/create_offer` | `/create_offer` | ✅ Already follows convention | Keep |
| `/offer_details` | `/view_offer` | Consistency with `view_` pattern | High |
| `/list_offers` | `/list_offers` | ✅ Already follows convention | Keep |
| `/update_offer_name` | `/update_offer_name` | ✅ Already follows convention | Keep |
| `/update_offer_price` | `/update_offer_price` | ✅ Already follows convention | Keep |
| `/update_offer_description` | `/update_offer_description` | ✅ Already follows convention | Keep |
| `/publish_offer` | `/publish_offer` | ✅ Specific workflow action | Keep |
| `/cancel_offer` | `/cancel_offer` | ✅ Already follows convention | Keep |
| `/delete_offer` | `/delete_offer` | ✅ Already follows convention | Keep |
| `/add_box` | `/create_box` | Consistency with `create_` pattern | Medium |
| `/audit_offer` | `/audit_offer` | ✅ Specific action verb | Keep |
| `/offer_status` | `/update_offer_status` | Clearer that it modifies status | Medium |

**Rationale**:
- `view_offer` is more intuitive than `offer_details`
- `create_box` aligns with other creation commands
- `update_offer_status` clarifies it's a modification action

---

### 4. Box Management Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/box_status` | `/list_boxes` | More accurate - lists multiple boxes | High |
| `/add_box` | `/create_box` | Consistency with `create_` pattern | Medium |

**Rationale**:
- `/box_status` actually lists boxes, not shows status of one box
- `list_boxes` better describes the actual functionality

---

### 5. Order Management Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/order` | `/create_order` (alias: `/order`) | Explicit action verb, keep short alias for UX | Medium |
| `/confirm_order` | `/confirm_order` | ✅ Specific workflow action | Keep |
| `/cancel_order` | `/cancel_order` | ✅ Already follows convention | Keep |
| `/my_orders` | `/list_my_orders` (alias: `/my_orders`) | Consistency with `list_` pattern, keep short alias for UX | Low |
| `/user_orders` | `/list_orders` | Shorter, clearer - context implies user orders | Medium |
| `/offer_orders` | `/list_offer_orders` | Consistency with `list_` pattern | Medium |
| `/all_orders` | `/export_orders` | Clearer - it exports CSV | High |
| `/order_for` | `/create_order_for` (alias: `/order_for`) | Explicit action verb, keep short alias for UX | Medium |
| `/order_wholesale` | `/process_wholesale` | Consistency with `process_` pattern | High |
| `/confirm_order_wholesale` | `/confirm_wholesale` | Shorter, clearer | Low |
| `/delete_cancelled` | `/delete_cancelled_orders` | More explicit object | Low |
| `/delete_completed` | `/delete_completed_orders` | More explicit object | Low |
| `/delete_old` | `/delete_old_orders` | More explicit object | Low |
| `/audit_orders` | `/audit_orders` | ✅ Already follows convention | Keep |
| `/import_orders` | `/import_orders` | ✅ Specific workflow action | Keep |
| `/finalize_import` | `/finalize_import` | ✅ Already follows convention | Keep |

**Rationale**:
- Adding `create_` prefix makes order creation explicit
- `/order` kept as permanent alias for customer convenience (high-frequency command)
- `/my_orders` kept as permanent alias for customer convenience (high-frequency command)
- `/order_for` kept as permanent alias for admin convenience (high-frequency command)
- `list_` prefix improves discoverability of viewing commands
- `export_orders` better describes CSV download functionality
- `process_wholesale` aligns with other workflow commands

---

### 6. User Management Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/pending_users` | `/list_pending` | Shorter, clearer - context implies pending users | Medium |
| `/list_users` | `/list_users` | ✅ Already follows convention | Keep |
| `/add_guest` | `/create_guest` | Consistency with `create_` pattern | Medium |
| `/list_guests` | `/list_guests` | ✅ Already follows convention | Keep |
| `/approve_user` | `/approve_user` | ✅ Already follows convention | Keep |
| `/reject_user` | `/reject_user` | ✅ Already follows convention | Keep |
| `/user_status` | `/view_user_status` | Consistency with `view_` pattern | Low |
| `/update_user` | `/update_user` | ✅ Already follows convention | Keep |
| `/update_user_first_name` | `/update_user_first_name` | ✅ Already follows convention | Keep |
| `/update_user_last_name` | `/update_user_last_name` | ✅ Already follows convention | Keep |
| `/subscribe` | `/subscribe` | ✅ Clear action | Keep |
| `/unsubscribe` | `/unsubscribe` | ✅ Clear action | Keep |

**Rationale**:
- `list_pending` is shorter and context makes it clear these are pending users
- `create_guest` aligns with entity creation pattern
- Most user commands already follow good conventions

---

### 7. Delivery & Fulfillment Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/wholesale_delivery` | `/process_delivery` | Shorter, clearer workflow | High |
| `/labeling_completed` | `/process_labeling` | Consistency with `process_` pattern | High |
| `/send_overviews` | `/send_invoices` | Clearer - sends delivery overview + payment link | Medium |
| `/mark_paid` | `/process_payment` | Consistency with `process_` pattern - multi-step workflow | Medium |
| `/failed_notifications` | `/list_failed_notifications` | Consistency with `list_` pattern | Low |

**Rationale**:
- `process_delivery` and `process_labeling` create consistent workflow naming
- More explicit names reduce ambiguity

---

### 8. Discount Management Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/create_discount` | `/create_discount` | ✅ Already follows convention | Keep |
| `/cancel_discount` | `/cancel_discount` | ✅ Already follows convention | Keep |
| `/discount_status` | `/view_discount` | Shorter, clearer - context implies discount status | Low |

**Rationale**: Discount commands already follow good conventions.

---

### 9. System & Maintenance Commands

| Current | Proposed | Reason | Priority |
|---------|----------|--------|----------|
| `/setup_test_data` | `/setup_test_data` | ✅ Clear purpose | Keep |

**Rationale**: System commands are clear and specific.

---

## Internal Callbacks (Not User-Facing)

These handlers are for button callbacks and should not be renamed as they're not user commands:

- `admin_*` (menu navigation)
- `*_selection` (UI callbacks)
- `*_page` (pagination)
- `*_select` (selection dialogs)
- `back_navigation`
- `complete_delivery`, `complete_labeling` (button actions)
- `delivery_action`, `labeling_action` (workflow steps)
- `document_upload`, `payment_link_input` (input handlers)
- `partial_action`, `incomplete_delivery_reply` (workflow branches)

---

## Migration Priority Matrix

### High Priority (User-Facing, High Frequency)
1. `/add_supplier` → `/create_supplier`
2. `/retire_supplier` → `/archive_supplier`
3. `/offer_details` → `/view_offer`
4. `/box_status` → `/list_boxes`
5. `/all_orders` → `/export_orders`
6. `/order_wholesale` → `/process_wholesale`
7. `/wholesale_delivery` → `/process_delivery`
8. `/labeling_completed` → `/process_labeling`

### Medium Priority (Consistency Improvements)
9. `/add_box` → `/create_box`
10. `/edit_supplier` → `/update_supplier`
11. `/offer_status` → `/update_offer_status`
12. `/order` → `/create_order`
13. `/order_for` → `/create_order_for`
14. `/user_orders` → `/list_user_orders`
15. `/offer_orders` → `/list_offer_orders`
16. `/pending_users` → `/list_pending`
17. `/add_guest` → `/create_guest`
18. `/send_overviews` → `/send_delivery_overviews`

### Low Priority (Nice to Have)
19. `/my_orders` → `/list_my_orders`
20. `/user_status` → `/view_user_status`
21. `/discount_status` → `/view_discount`
22. `/failed_notifications` → `/list_failed_notifications`
23. `/delete_cancelled` → `/delete_cancelled_orders`
24. `/delete_completed` → `/delete_completed_orders`
25. `/delete_old` → `/delete_old_orders`

### Phase 4: Documentation & Future Improvements (Optional)

**Goal:** Complete documentation and address any remaining improvements

**Documentation Updates:**
- [ ] Update README.md Bot Commands section with new names
- [ ] Update any external documentation
- [ ] Create migration guide for users (if needed)
- [ ] Document permanent aliases in README

**Future Improvements (Out of Scope):**
- Consider implementing command autocomplete in Telegram
- Add command aliases to help text
- Create visual command reference guide
- Implement command usage analytics

---

## Work Items Discovered During Implementation

During Phase 1 implementation, the following work items were identified:

### ✅ RESOLVED: Callback Handler Updates
Initially discovered that callback handlers needed updating, but this was fixed in Phase 1 to prevent broken functionality. Updated 15 callback keys in `src/services/callback_handler.py` command_map.

### Phase 2 Requirements
1. **Admin Panel Callbacks**: Update callback handlers in admin panel that reference old command names
2. **Handler References**: Search codebase for hardcoded command strings in handlers (e.g., help text generation)
3. **Deep Link Generation**: Update any code that generates deep links with old command names
4. **Error Messages**: Update error messages that reference specific commands
5. **Logging**: Update log messages that reference command names

### Translation Keys to Update
The following translation keys will need updates in Phase 2:
- Command descriptions in help text
- Usage examples
- Error messages referencing commands
- Admin panel button labels
- Command aliases documentation

### Files to Review in Phase 2
- `src/translations/en.json`
- `src/translations/nl.json`
- `setup-commands.sh`
- `src/handlers/admin_commands_handler.py` (admin panel callbacks)
- `src/handlers/info_handler.py` (help text generation)
- Any handlers that generate deep links

---

## Implementation Plan

### Phase 0: Test Current System ✅ COMPLETE
**CRITICAL: Write tests for existing commands BEFORE any refactoring**

- [x] **Write comprehensive command routing tests for ALL current commands**
- [x] Test current command names route to correct handlers
- [x] Test parameter parsing for each current command
- [x] Test parameter validation (types, ranges, required/optional)
- [x] Test error handling for invalid commands
- [x] Ensure 100% test coverage of command routing
- [x] Document current behavior as baseline

**Implementation Details:**
- Created `tests/test_command_routing.py` with 89 test cases (expanded from 63)
- Tests verify ACTUAL CommandRouter code logic (not just mocked handlers)
- Tests command parsing: bot mention stripping, parameter extraction
- Tests authorization logic: admin vs customer, approved vs unauthorized
- Tests routing decisions: correct handler called for each command
- Tests deep link handling: /start with order/confirm/help parameters
- Tests filter parsing: status filters and search strings
- Tests environment behavior: test vs production group handling
- Tests permanent aliases: order, my_orders, order_for
- Tests old command rejection: ensures deprecated commands return unknown_command
- Uses pytest with parametrized tests for efficiency
- Handlers mocked to isolate router logic being tested

**Test Coverage:**
- Command parsing (bot mentions, parameters)
- Authorization (admin access, user approval status)
- Routing (all customer and admin commands)
- Deep links (/start with parameters)
- Filter parsing (list_suppliers, list_users)
- Unknown command handling
- Permanent alias routing
- Old command rejection

**Rationale**: These tests serve as:
1. **Regression prevention** - Catch any breaking changes during refactoring
2. **Documentation** - Living documentation of how commands work
3. **Confidence** - Safe refactoring with immediate feedback
4. **Baseline** - Clear understanding of current system before changes

### Phase 1: Refactoring ✅ COMPLETE
- [x] Update command router with new command names
- [x] Implement permanent aliases (order, my_orders, order_for)
- [x] Update callback handler command_map keys
- [x] Update pagination parsing for multi-word commands
- [x] Update tests to reflect new command names
- [x] Add tests for permanent alias routing
- [x] Add tests for old command rejection
- [x] Add comprehensive callback routing tests (62 tests)
- [x] Integrate callback routing tests into deploy.sh
- [x] Verify all tests pass (212/212 passing)
- [x] Document all affected translation keys

**Implementation Summary:**
- Updated `src/services/command_router.py` with new command names
- Updated `src/services/callback_handler.py` command_map with 15 new callback keys
- Fixed pagination parsing for multi-word commands (process_payment, list_user_orders, list_my_orders)
- Maintained backward compatibility for existing pagination callbacks
- Added PERMANENT_ALIASES dictionary for high-frequency commands
- Implemented alias resolution in route_command method
- Updated deep link handling for new command names
- Created `tests/test_callback_routing.py` with 62 comprehensive tests
- All 212 tests passing including:
  - 89 command routing tests (updated for new names)
  - 62 callback routing tests (NEW)
  - 3 permanent alias tests
  - 20 old command rejection tests
  - 61 integration tests

**Commands Renamed:**
- `/add_supplier` → `/create_supplier`
- `/retire_supplier` → `/archive_supplier`
- `/edit_supplier` → `/update_supplier`
- `/offer_details` → `/view_offer`
- `/add_box` → `/create_box`
- `/box_status` → `/list_boxes`
- `/order_wholesale` → `/process_wholesale`
- `/order_for` → `/create_order_for` (alias: `/order_for`)
- `/user_orders` → `/list_user_orders`
- `/offer_orders` → `/list_offer_orders`
- `/all_orders` → `/export_orders`
- `/pending_users` → `/list_pending`
- `/add_guest` → `/create_guest`
- `/discount_status` → `/view_discount`
- `/wholesale_delivery` → `/process_delivery`
- `/labeling_completed` → `/process_labeling`
- `/send_overviews` → `/send_delivery_overviews`
- `/mark_paid` → `/process_payment`
- `/delete_old` → `/delete_old_orders`
- `/delete_cancelled` → `/delete_cancelled_orders`
- `/delete_completed` → `/delete_completed_orders`
- `/order` → `/create_order` (alias: `/order`)
- `/my_orders` → `/list_my_orders` (alias: `/my_orders`)

**Permanent Aliases (for UX):**
- `/order` → `/create_order`
- `/my_orders` → `/list_my_orders`
- `/order_for` → `/create_order_for`

### Phase 2: User-Facing Updates (✅ COMPLETE)

**Goal:** Update all user-facing elements to reflect new command names

**High Priority:**
- [x] Update translation files (en.json, nl.json) with new command names
- [x] Update setup-commands.sh script with new Telegram command list
- [x] Update help text generation (via translation files)
- [x] Update usage messages for all renamed commands
- [x] Rename translation keys to match new command names
- [x] Update code references to new translation keys
- [x] Test in test environment thoroughly (all 152 tests passing)

**Deliverables:**
- ✅ Updated translation files with 18 keys each (10 help text + 8 usage messages)
- ✅ Renamed 8 translation keys for consistency (usage_add_supplier → usage_create_supplier, etc.)
- ✅ Updated setup-commands.sh with 23 new command names
- ✅ Updated 3 handler files with new translation key references
- ✅ All 152 routing tests passing

**Key Improvements:**
- Translation keys now match command names for automatic consistency
- Usage messages display correct command names
- Help text updated across all sections
- No hardcoded command references found in codebase

### Phase 3: Production Deployment & Verification ✅ COMPLETE

**Goal:** Deploy to production and verify all functionality

**Pre-Deployment Checklist:**
- [x] Run full test suite (all 151 tests passing) ✅
- [x] Update README.md with new command names ✅
- [x] Create admin notification message ✅
- [x] Create changelog entry ✅
- [x] Create comprehensive deployment checklist ✅
- [x] Manual testing of critical workflows in test environment ✅
- [x] Verify permanent aliases work correctly (order, my_orders, order_for) ✅
- [x] Comprehensive integration testing ✅

**Deployment Steps:**
1. [x] Deploy to test environment: `./deploy.sh test` ✅
2. [x] Verify test environment functionality ✅
3. [x] Deploy to production: `./deploy.sh prod` ✅
4. [x] Update Telegram command list via BotFather ✅
5. [x] Monitor logs for errors ✅
6. [x] Verify webhook functionality ✅

**Post-Deployment Verification:**
- [x] Test all renamed commands in production ✅
- [x] Test permanent aliases (order, my_orders, order_for) ✅
- [x] Verify old commands return unknown_command ✅
- [x] Test admin panel buttons ✅
- [x] Test pagination for multi-word commands ✅
- [x] Verify help text displays correctly ✅
- [x] Verify usage messages show correct commands ✅

**Success Criteria:**
- ✅ All 23 renamed commands work correctly
- ✅ Permanent aliases function properly
- ✅ Old commands properly rejected
- ✅ Help text shows new command names
- ✅ Usage messages show new command names
- ✅ No errors in CloudWatch logs

**Status: DEPLOYMENT COMPLETE**

All phases of the command naming standardization project have been successfully completed.

---

## Backward Compatibility Strategy

### Permanent Aliases Only

**Only these aliases will be implemented for UX convenience:**

```python
PERMANENT_ALIASES = {
    'order': 'create_order',  # High-frequency customer command
    'my_orders': 'list_my_orders',  # High-frequency customer command
    'order_for': 'create_order_for',  # High-frequency admin command
}
```

**All other renamed commands will NOT have backward compatibility aliases.**

Users and admins will need to use the new command names immediately after deployment. This ensures:
- Clean codebase without legacy baggage
- Faster adoption of new naming convention
- No confusion between old and new commands
- Simpler maintenance

### Migration Communication

- Update help text with new commands before deployment
- Send announcement to admin about command changes
- Update Telegram command list via BotFather
- Document changes in changelog

---

## Translation Key Updates Required

### Keys to Add
- All new command names in help text
- Deprecation warning messages
- Command alias hints

### Keys to Update
- Command descriptions
- Usage examples
- Help section text
- Admin menu button labels

---

## Testing Checklist

### Command Routing Tests
- [ ] All command names route to correct handlers
- [ ] All parameter parsing works correctly
- [ ] Required parameters validated
- [ ] Optional parameters handled
- [ ] Parameter types validated (int, string, etc.)
- [ ] Parameter value ranges validated
- [ ] Invalid parameter values rejected
- [ ] Missing required parameters rejected
- [ ] Permanent aliases route correctly (order, my_orders, order_for)
- [ ] Old command names return "unknown command" error

### Integration Tests
- [ ] Help text displays new commands
- [ ] Telegram command list updated
- [ ] Admin menu buttons use new commands
- [ ] Translation keys exist for both languages
- [ ] No broken references in codebase
- [ ] Documentation updated

### Example Test Cases

```python
def test_create_supplier_routing():
    """Test /create_supplier routes correctly with parameters"""
    assert route_command('create_supplier', ['TestSupplier']) == 'handle_create_supplier'
    assert validate_params('create_supplier', ['TestSupplier']) == True
    assert validate_params('create_supplier', []) == False  # Missing required param

def test_create_order_with_alias():
    """Test /order alias routes to create_order"""
    assert route_command('order', ['123', '2']) == 'handle_create_order'
    assert route_command('create_order', ['123', '2']) == 'handle_create_order'

def test_list_boxes_with_filters():
    """Test /list_boxes with optional filter parameters"""
    assert route_command('list_boxes', []) == 'handle_list_boxes'
    assert route_command('list_boxes', ['active']) == 'handle_list_boxes'
    assert route_command('list_boxes', ['123']) == 'handle_list_boxes'
    assert validate_params('list_boxes', ['invalid_filter']) == False

def test_old_command_rejected():
    """Test old command names are rejected"""
    assert route_command('add_supplier', ['Test']) == None
    assert route_command('box_status', []) == None
```

---

## Benefits Summary

1. **Improved Discoverability**: Consistent patterns make commands easier to find
2. **Reduced Cognitive Load**: Users learn one pattern, apply everywhere
3. **Better Maintainability**: Clear naming makes code easier to understand
4. **Professional Polish**: Consistent naming improves perceived quality
5. **Easier Onboarding**: New users learn system faster
6. **Future-Proof**: Scalable naming convention for new features

---

## Estimated Impact

- **Commands Renamed**: 23 (implemented in Phase 1)
- **Commands Kept**: 67 (already follow good conventions)
- **Permanent Aliases**: 3 (order, my_orders, order_for)
- **Translation Keys to Update**: ~150 (Phase 2)
- **Code Files Modified**: 8 (Phase 1 complete)
- **Tests Written**: 151 routing tests (Phase 1 complete)
- **Total Tests**: 212 (all passing)
- **Estimated Remaining Effort**: 2-3 weeks (Phases 2-3)
- **User Impact**: High - requires immediate adaptation to new commands (except permanent aliases)
