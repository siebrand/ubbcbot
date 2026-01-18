# Refactoring Plan: Callback Handler

## Problem Statement
The `src/services/callback_handler.py` file contains a massive `handle_callback_query` method (~700 lines) that acts as a central switch statement for all Telegram callback button interactions.
- **Complexity:** A giant `if/elif/else` chain makes it hard to trace execution flow.
- **Fragility:** String parsing (e.g., `data.split('_')`) is repeated and error-prone.
- **Violation of Open/Closed Principle:** Adding a new callback requires modifying this central file.

## Goal
Implement a **Callback Router** mechanism to decouple callback parsing from execution. Handlers should register themselves for specific patterns.

## Proposed Architecture

### 1. Callback Router
A class responsible for matching callback data to a handler function.

```python
class CallbackRouter:
    def __init__(self):
        self.routes = []

    def register(self, pattern: str, handler_func):
        # Store regex pattern and handler
        pass

    def dispatch(self, callback_data: str, context):
        # Match data against patterns and call the correct handler
        pass
```

### 2. Handler Registration
Handlers (e.g., in `src/handlers/admin/order_commands.py`) should register their interest in specific callback patterns.

```python
# Example in AdminOrderHandler
@callback_handler(pattern=r"^order_for_quantity_(\d+)_(\d+)_(\d+)$")
def handle_order_quantity(self, match, chat_id, user_id):
    customer_id, offer_id, qty = match.groups()
    # Logic...
```

### 3. Structured Callback Data
Standardize callback data format to avoid ad-hoc parsing like `parts[3]`.

## Refactoring Steps

1.  **Create Router Infrastructure:**
    - Create `src/services/routing/callback_router.py`.
    - Implement regex-based matching.

2.  **Define Patterns:**
    Analyze `callback_handler.py` to list all current string patterns (e.g., `wd_`, `page_`, `confirm_process_wholesale_`).

3.  **Iterative Migration:**
    - **Phase 1: Admin Callbacks**
      - Move admin-related `elif` blocks to their respective handlers using the new router.
    - **Phase 2: Order Callbacks**
      - Move complex order parsing logic to `OrderHandler`.
    - **Phase 3: Pagination**
      - Create a generic `PaginationHandler` to handle `page_` callbacks.

4.  **Update Main Handler:**
    Replace the giant `if/elif` in `CallbackHandler.handle_callback_query` with:
    ```python
    def handle_callback_query(self, callback_query):
        data = callback_query['data']
        if self.router.dispatch(data, context):
            return
        # fallback...
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