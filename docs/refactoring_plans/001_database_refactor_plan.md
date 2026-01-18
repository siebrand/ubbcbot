# Refactoring Plan: Database Service

## Problem Statement
The `src/services/database.py` file currently houses the `DynamoDBService` class, which acts as a "God Class" for the application's persistence layer. It currently contains:
- 1300+ lines of code.
- Direct initialization of 12+ DynamoDB tables.
- Mixed responsibilities: Table management, CRUD operations for all entities (Suppliers, Offers, Orders, etc.), ID generation, and caching side-effects.
- High coupling: Changes to any entity's storage logic require modifying this single giant file.

## Goal
Decompose `DynamoDBService` into smaller, focused **Repository** classes, following the Repository Pattern. This will improve maintainability, testability, and separation of concerns.

## Proposed Architecture

### 1. Base Repository
Create a `BaseRepository` class to handle common DynamoDB operations (connection, error handling, serialization).

```python
class BaseRepository:
    def __init__(self, table_name: str):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)

    def _prepare_item(self, item: Dict) -> Dict:
        # Common serialization logic
        pass
```

### 2. Specialized Repositories
Create specific repositories for each domain entity in a new `src/repositories/` directory.

- `SupplierRepository`
- `OfferRepository` (will also handle `OfferCache` invalidation)
- `CustomerRepository`
- `OrderRepository`
- `CreditRepository` (for `CustomerCredit`, `CreditTransaction`)
- `OrderHistoryRepository` (for `OrderHistory` - potentially part of OrderRepository)
- `BoxRepository`
- `SystemRepository` (counters, audit logs, etc.)
- `DiscountRepository`
- `NotificationRepository`
- `EditContextRepository`

### 3. Service Layer Adjustment
The `DynamoDBService` can be retained temporarily as a facade to maintain backward compatibility, or the application can be updated to inject specific repositories where needed.

## Refactoring Steps & Status

1.  **Create Directory Structure:** [x] Done
    ```
    src/
    ├── repositories/
    │   ├── __init__.py
    │   ├── base_repository.py
    │   ├── supplier_repository.py
    │   ├── offer_repository.py
    │   └── ...
    ```

2.  **Extract Base Logic:** [x] Done
    - `BaseRepository` implemented with `_prepare_item` and `_serialize_datetime`.

3.  **Iterative Extraction:**
    - [x] **Phase 1: Suppliers**
      - `SupplierRepository` created.
      - `DynamoDBService` delegates supplier operations.
    - [x] **Phase 2: Offers**
      - `OfferRepository` created.
      - `OfferCache` invalidation preserved.
      - `DynamoDBService` delegates offer operations.
    - [x] **Phase 3: Customers**
      - `CustomerRepository` created.
      - `UserCache` interaction handled.
      - `DynamoDBService` delegates customer operations.
    - [x] **Phase 4: Boxes**
      - `BoxRepository` created.
      - All box CRUD operations extracted.
      - `DynamoDBService` delegates box operations.
      - Comprehensive unit tests added (9 test cases, all passing).
    - [x] **Phase 5: Orders**
      - `OrderRepository` created using TDD.
      - Core order CRUD operations extracted.
      - `DynamoDBService` delegates order operations.
      - Audit logging preserved in facade layer.
      - Comprehensive unit tests added (10 test cases, all passing).
    - [x] **Phase 6: Order History**
      - `OrderHistoryRepository` created using TDD.
      - All order history operations extracted.
      - `DynamoDBService` delegates order history operations.
      - Datetime conversion utility added for DynamoDB compatibility.
      - Comprehensive unit tests added (7 test cases, all passing).

## Pending Tasks

### Phase 7: Credits (Next)
- [ ] Create `CreditRepository`.
- [ ] Move `create_customer_credit`, `get_customer_credit`, `update_customer_credit`.
- [ ] Move `create_credit_transaction`, `get_credit_transactions_...`.
- [ ] Update `DynamoDBService`.

### Phase 8: System & Misc
- [ ] Expand `SystemRepository` or create specific repos for:
    - [ ] `DiscountsTable` -> `DiscountRepository`
    - [ ] `NotificationsTable` -> `NotificationRepository`
    - [ ] `EditContextsTable` -> `EditContextRepository`
- [ ] Clean up `DynamoDBService` imports and table initializations.

## Risk Assessment

### 1. Data Integrity & Loss
*   **Risk:** High. Incorrect serialization or table naming during the migration could lead to data being written to the wrong location or in the wrong format.
*   **Mitigation:** rigorous unit tests using `moto` to verify that data written by the new repository is byte-for-byte identical to data written by the old service.

### 2. Business Logic Regression
*   **Risk:** Medium. Some methods in `database.py` might contain hidden business logic (e.g., side effects like updating counters or invalidating caches) that could be missed during extraction.
*   **Mitigation:** Carefully audit each method for side effects before moving. Ensure `OfferCache` invalidation calls are preserved in the `OfferRepository`.

### 3. Runtime Errors
*   **Risk:** Low/Medium. Circular imports could occur if repositories need to reference each other.
*   **Mitigation:** Use dependency injection and avoid direct imports between repositories.

## TDD Requirements

Before writing any production code, the following test infrastructure and procedure must be established:

### 1. Test Infrastructure (`conftest.py`)
*   [x] Ensure `moto` is configured to mock DynamoDB interactions.
*   [x] Create a fixture that initializes the table structure exactly as `DynamoDBService` does.

### 2. Development Cycle (For each Entity)
1.  **Write Parity Test:** Create a test case that:
    *   Instantiates the *legacy* `DynamoDBService`.
    *   Performs an operation (e.g., `create_supplier`).
    *   Asserts the state of the DynamoDB table.
2.  **Write New Repository Test:** Create a mirror test case that:
    *   Instantiates the *new* `SupplierRepository`.
    *   Performs the same operation.
    *   Asserts the state of the DynamoDB table is *identical* to the legacy test.
3.  **Implement Repository:** Write the `SupplierRepository` code to pass the test.
4.  **Integration Test:** Update the `DynamoDBService` facade to use the new repository and verify existing application tests still pass.

### 3. Error Handling Tests
*   Write tests for DynamoDB exceptions (e.g., `ClientError`, `ItemNotFound`).
*   Ensure the new repositories raise consistent, typed exceptions rather than raw Boto3 errors.

## Benefits
- **Single Responsibility:** Each repository handles one entity.
- **Testability:** Easier to mock individual repositories than the entire DB service.
- **Scalability:** New entities can be added without bloating a central file.