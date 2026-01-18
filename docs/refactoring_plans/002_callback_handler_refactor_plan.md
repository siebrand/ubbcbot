# Refactoring Plan: Callback Handler

## Problem Statement
The `src/services/callback_handler.py` file contains a massive `handle_callback_query` method (~700 lines) that acts as a central switch statement for all Telegram callback button interactions.
- **Complexity:** A giant `if/elif/else` chain makes it hard to trace execution flow.
- **Fragility:** String parsing (e.g., `data.split('_')`) is repeated and error-prone.
- **Violation of Open/Closed Principle:** Adding a new callback requires modifying this central file.

## Goal
Implement a **Callback Router** mechanism to decouple callback parsing from execution. Handlers should register themselves for specific patterns.

## Proposed Architecture

### 1. Callback Router with Alias Support
A class responsible for matching callback data to a handler function, with built-in support for command shortcuts/aliases.

```python
class CallbackRouter:
    def __init__(self):
        self.routes = []  # List of (compiled_regex, handler_func, aliases)

    def register(self, pattern: str, handler_func, aliases: list = None):
        """
        Register a callback handler.
        
        Args:
            pattern: Regex pattern (e.g., r"^approve_(\d+)$")
            handler_func: Function to call when matched
            aliases: Optional list of alternative patterns
                    (e.g., [r"^appr_(\d+)$", r"^a_(\d+)$"])
        """
        compiled = re.compile(pattern)
        self.routes.append((compiled, handler_func, pattern))
        
        # Register aliases pointing to same handler
        if aliases:
            for alias in aliases:
                compiled_alias = re.compile(alias)
                self.routes.append((compiled_alias, handler_func, alias))

    def dispatch(self, callback_data: str, context):
        """
        Match callback_data against registered patterns.
        Returns True if handled, False otherwise.
        """
        for regex, handler, pattern_str in self.routes:
            match = regex.match(callback_data)
            if match:
                handler(match, context)
                return True
        return False
```

**Alias Benefits:**
- Shorter callback data = less Telegram API payload
- Faster typing for power users (if exposed as commands)
- Backward compatibility when renaming callbacks
- Example: `approve_123` → `appr_123` → `a_123`

### 2. Handler Registration with Aliases
Handlers (e.g., in `src/handlers/admin/order_commands.py`) should register their interest in specific callback patterns, optionally with shortcuts.

```python
# Example in AdminOrderHandler
@callback_handler(
    pattern=r"^order_for_quantity_(\d+)_(\d+)_(\d+)$",
    aliases=[
        r"^ofq_(\d+)_(\d+)_(\d+)$",  # Short form
        r"^oq_(\d+)_(\d+)_(\d+)$"    # Ultra-short form
    ]
)
def handle_order_quantity(self, match, chat_id, user_id):
    customer_id, offer_id, qty = match.groups()
    # Logic...
```

**Alias Strategy:**
- Start with full names during migration
- Add aliases in Phase 3 after patterns stabilize
- Document alias mappings in `docs/callback_aliases.md`
- Consider Telegram's 64-byte callback_data limit when designing aliases

### 3. Structured Callback Data
Standardize callback data format to avoid ad-hoc parsing like `parts[3]`.

## Refactoring Steps

### Gradual Alphabetical Migration Strategy
To minimize risk and allow incremental testing, we'll migrate callbacks **alphabetically by prefix**, starting with a single pattern, then expanding to 3, then completing the rest.

**Migration Phases:**
- **Phase 0:** Infrastructure setup (router + tests)
- **Phase 1:** Single pattern (e.g., `approve_` callbacks)
- **Phase 2:** Three patterns (e.g., `approve_`, `cancel_`, `confirm_`)
- **Phase 3:** Remaining patterns in alphabetical batches

This allows:
- Testing router in production with minimal risk
- Rolling back easily if issues arise
- Learning from early patterns to improve later ones

### Detailed Steps

1.  **Create Router Infrastructure (Phase 0):**
    - Create `src/services/routing/callback_router.py`.
    - Implement regex-based matching with **alias support** (see below).
    - Add comprehensive unit tests.

2.  **Catalog All Patterns:**
    Analyze `callback_handler.py` to list all current string patterns alphabetically:
    ```
    approve_, archive_supplier_, cancel_, confirm_, create_box_,
    delete_, edit_, finalize_import_, list_, order_for_, page_,
    process_, publish_, reject_, select_, toggle_, update_, view_, wd_
    ```

3.  **Phase 1 - Single Pattern Migration:**
    - Choose simplest pattern: `approve_<user_id>`
    - Implement handler registration in `AdminUserHandler`
    - Update `CallbackHandler` to check router first, then fallback to existing logic
    - Deploy and monitor

4.  **Phase 2 - Three Pattern Migration:**
    - Add `cancel_<action>` patterns
    - Add `confirm_<action>` patterns
    - Test interaction between patterns
    - Deploy and monitor

5.  **Phase 3 - Batch Migration:**
    - Migrate remaining patterns in alphabetical groups of 5-7
    - Each batch: implement → test → deploy → monitor
    - Final batch removes fallback logic entirely

6.  **Update Main Handler:**
    Replace the giant `if/elif` in `CallbackHandler.handle_callback_query` with:
    ```python
    def handle_callback_query(self, callback_query):
        data = callback_query['data']
        if self.router.dispatch(data, context):
            return
        # fallback to legacy handler (remove after full migration)
        self._legacy_handler(data, context)
    ```

## Risk Assessment

### 1. Functional Regression
*   **Risk:** High. Incorrect regex patterns could fail to match valid callbacks, effectively breaking buttons in the UI. Overlapping regex patterns (e.g., `^order_` vs `^order_for_`) could route commands to the wrong handler.
*   **Mitigation:** Define patterns strictly with start (`^`) and end (`$`) anchors where possible. Order registration from most specific to least specific.

### 2. Context Loss
*   **Risk:** Medium. The current monolithic handler might be implicitly passing state or context (like `edit_context_manager`) that could be lost when moving to isolated handlers.
*   **Mitigation:** Ensure the `dispatch` method passes the full context object (db, user_id, chat_id, message_id) to the handlers.

### 3. Performance
*   **Risk:** Low. Regex matching is generally fast, but a very large list of poorly optimized regexes could theoretically add latency.
*   **Mitigation:** Compile regex patterns on registration.

## TDD Requirements

### 1. Router Logic Tests
*   **Test Registration:** Verify that handlers can be registered with patterns.
*   **Test Matching:** Verify that a data string correctly matches its registered pattern and extracts groups.
*   **Test No Match:** Verify behavior when no pattern matches (should return False or None).
*   **Test Priority:** (If applicable) Verify that the first matching route is taken.

### 2. Migration Tests (Per Handler)
For every block of logic moved from the `if/elif` chain:

1.  **Capture Baseline:** Identify an example callback string (e.g., `order_for_quantity_123_456_5`).
2.  **Write Route Test:**
    ```python
    def test_order_quantity_routing():
        router = CallbackRouter()
        handler = Mock()
        router.register(r"^order_for_quantity_(\d+)_(\d+)_(\d+)$", handler)
        
        router.dispatch("order_for_quantity_123_456_5", context)
        
        handler.assert_called_with(match_object, context)
        assert match_object.groups() == ('123', '456', '5')
    ```
3.  **Implement Handler:** Move the logic to the registered function.
4.  **Verify Integration:** Ensure the `CallbackHandler` delegates to the router for this pattern.

## Benefits
- **Decoupling:** `CallbackHandler` no longer needs to know about every specific feature.
- **Readability:** Logic is co-located with the feature handler (e.g., order logic stays in `OrderHandler`).
- **Safety:** Regex matching is more robust than manual string splitting.
- **Gradual Migration:** Alphabetical phasing allows production testing with minimal risk.
- **Future-Proof:** Alias support enables command shortening without breaking existing buttons.
- **Payload Optimization:** Shorter callbacks reduce Telegram API data transfer.

## Alphabetical Pattern Catalog

Based on analysis of `callback_handler.py`, here are all callback prefixes in alphabetical order:

```
Phase 1 (Single - Simplest):
  ✅ approve_user_<customer_id> - COMPLETED
  ✅ approve_user_select_<customer_id> - COMPLETED

Phase 2 (User Actions & Confirmations):
  ✅ reject_user_<customer_id> - COMPLETED
  ✅ cancel_order_user_select_<customer_id> - COMPLETED
  ✅ cancel_order_confirm_<order_id> - COMPLETED
  ✅ cancel_orders_page_<customer_id>_<page> - COMPLETED
  ✅ cancel_confirmation - COMPLETED
  ✅ cancel_action - COMPLETED
  ✅ confirm_process_wholesale_<offer_id>_<boxes> - COMPLETED
  ✅ confirm_cancel_offer_<offer_id> - COMPLETED
  ✅ confirm_cancel_order_<order_id> - COMPLETED
  ✅ confirm_fulfill_<offer_id>_<boxes> - COMPLETED
  ✅ confirm_order_<offer_id>_<quantity> - COMPLETED

Phase 3 (Remaining - Alphabetical Batches):
  Batch A (Edit patterns):
    ✅ edit_user_select_<customer_id> - COMPLETED
    ✅ edit_supplier_select_<supplier_id> - COMPLETED
    ✅ edit_<entity>_<field>_<id> - COMPLETED
  
  Batch B (Order patterns):
    ☐ order_for_offer_<customer_id>_<offer_id>
    ☐ order_for_quantity_<customer_id>_<offer_id>_<quantity>
    ☐ order_for_other_<customer_id>_<offer_id>
    ☐ order_for_user_select_<customer_id>
    ☐ order_<offer_id>_<quantity>
  
  Batch C (Offer/Supplier patterns):
    ☐ wholesale_select_<offer_id>
    ☐ custom_wholesale_quantity_<offer_id>
    ☐ publish_offer_<offer_id>
    ☐ finalize_import_<offer_id>
    ☐ offer_details_<offer_id>
    ☐ offer_orders_<offer_id>
    ☐ upload_offer_image_<offer_id>
    ☐ clear_offer_images_<offer_id>
  
  Batch D (User/Status patterns):
    ☐ user_orders_select_<customer_id>
    ☐ user_status_select_<customer_id>
    ☐ credit_customer_<customer_id>
    ☐ enter_username_<action>
  
  Batch E (Audit patterns):
    ☐ audit_offer_<offer_id>
    ☐ audit_fill_boxes_<offer_id>_<excess>
    ☐ audit_fill_create_<offer_id>_<excess>
    ☐ audit_create_boxes_<offer_id>_<excess>
    ☐ audit_cancel_orders_<offer_id>_<excess>
  
  Batch F (Delivery/Export patterns):
    ☐ export_orders_<status>
    ☐ start_send_overviews
    ☐ finish_labeling_<box_id>
    ☐ mark_paid_<customer_id>
    ☐ request_cancel_reason_<order_id>
  
  Batch G (Navigation patterns):
    ☐ back_to_supplier_list
    ☐ process_wholesale
    ☐ create_supplier_start

Note: page_, admin, cmd, wd_, and lc_ patterns use different formats (colon-separated)
and may require separate handling or can remain in dedicated methods.
```on>_<params>
    - publish_<entity>_<id>
    - reject_<user_id>
  
  Batch D:
    - select_<entity>_<id>_<params>
    - toggle_<setting>_<params>
    - update_<entity>_<id>_<params>
  
  Batch E:
    - view_<entity>_<id>
    - wd_<offer_id>_<box_id>_<quantity>  (wholesale delivery)
```

## Migration Status

### ✅ Phase 0: Infrastructure Setup (COMPLETED)
**Commits:**
- `test: add CallbackRouter infrastructure tests (TDD red phase)` - 12d2203
- `feat: implement CallbackRouter infrastructure (TDD green phase)` - b76ec21

**Deliverables:**
- `src/services/routing/callback_router.py` - Router implementation
- `tests/test_callback_router.py` - 10 unit tests
- Built-in alias support for future command shortcutting
- All infrastructure tests passing

### ✅ Phase 1: Single Pattern Migration (COMPLETED)
**Commits:**
- `test: add approve_user callback migration tests (Phase 1)` - 3bd7ee7
- `feat: migrate approve_user callbacks to router (Phase 1 complete)` - 4c01271

**Deliverables:**
- `tests/test_approve_callback_migration.py` - 6 integration tests
- Router integrated into CallbackHandler
- Migrated patterns:
  - `approve_user_<customer_id>` → `handle_approve_user_by_id`
  - `approve_user_select_<customer_id>` → `handle_approve_user_select`
- Removed legacy if/elif blocks for approve callbacks
- All 78 callback tests passing (62 existing + 16 new)

**Key Learnings:**
- Pattern order matters: register more specific patterns first
- Use negative character class `[^_]` to prevent overlap (e.g., `approve_user_[^_]+` won't match `approve_user_select_`)
- Router dispatch must happen after callback answer but before keyboard removal
- Customer IDs are UUIDs (alphanumeric), not just digits

**Testing in Production:**
1. Test approve user flow: `/list_pending` → click approve button
2. Test approve user search: Admin panel → Users → Approve User → enter username → approve
3. Monitor CloudWatch logs for "Callback handled by router" messages

### ☐ Phase 2: Three Pattern Migration (NEXT)
**Target Patterns:**
1. `cancel_<action>` - Various cancellation callbacks
2. `confirm_<action>_<params>` - Confirmation callbacks  
3. `archive_supplier_<supplier_id>` - Supplier archival

**Estimated Effort:** 2-3 commits following same TDD pattern

### ☐ Phase 3: Batch Migration (FUTURE)
**Remaining Patterns:** See catalog above
**Estimated Effort:** 10-15 commits (2-3 patterns per commit)

## Migration Checklist Template

For each pattern/batch:
- [ ] Document current callback format and parameters
- [ ] Write router registration test
- [ ] Implement handler with router registration
- [ ] Add integration test (end-to-end button click)
- [ ] Deploy to test environment
- [ ] Verify in test Telegram bot
- [ ] Deploy to production
- [ ] Monitor CloudWatch logs for 24-48 hours
- [ ] (Optional) Add aliases for frequently-used callbacks
- [ ] Update documentation

## Metrics

| Metric | Before | After Phase 1 | Target (Complete) |
|--------|--------|---------------|-------------------|
| Callback patterns in if/elif | ~50 | ~48 | 0 |
| Callback patterns in router | 0 | 2 | ~50 |
| Lines in handle_callback_query | ~700 | ~695 | ~100 |
| Test coverage | 62 tests | 78 tests | ~120 tests |
