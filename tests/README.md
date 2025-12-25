# UBBC Bot Test Suite

Comprehensive tests covering all commands and use cases including failure scenarios.

## Test Structure

```
tests/
├── __init__.py                 # Package marker
├── run_tests.py               # Test runner
├── test_add_box.py           # Add box command tests
├── test_commands.py          # General command tests
├── test_customer_orders.py   # Customer order scenarios
└── test_admin_operations.py  # Admin operation tests
```

## Running Tests

```bash
# Run all tests
python3 tests/run_tests.py

# Run individual test files
python3 tests/test_commands.py
python3 tests/test_customer_orders.py
python3 tests/test_admin_operations.py
python3 tests/test_add_box.py
```

## Test Coverage

### 1. Add Box Command (`test_add_box.py`)
- ✅ Sold out offer becomes active
- ✅ Active offer remains active

### 2. General Commands (`test_commands.py`)
- ✅ Order placement restrictions for ordered/completed/delivered offers
- ✅ Box status transitions (open → minimum → full)
- ✅ Offer status transitions (active ↔ sold out)
- ✅ Order limits (customer: 5 units, admin: 10 units)
- ✅ Validation failures (invalid box sizes, negative quantities, empty/long names)

### 3. Customer Orders (`test_customer_orders.py`)
- ✅ Order execution and total calculation
- ✅ Capacity checking and box fitting
- ✅ Duplicate order handling and confirmation
- ✅ Order status updates (pending → ordered/cancelled)
- ✅ Notification scenarios (private vs group chat)
- ✅ Sold out detection

### 4. Admin Operations (`test_admin_operations.py`)
- ✅ Fulfillment calculations and partial fulfillment
- ✅ Offer cancellation with order cleanup
- ✅ Individual order cancellation and inventory correction
- ✅ Notification message cleanup (48-hour rule)
- ✅ Box management (creation/deletion)
- ✅ Status validations

## Failure Scenarios Tested

### Validation Failures
- Invalid box sizes (not in [1,2,6,8,10,12,15,16,18,20,24])
- Negative quantities
- Empty offer names
- Names exceeding 100 characters

### Business Logic Failures
- Order exceeds customer limit (5 units)
- Insufficient capacity
- Box creation blocked for ordered/completed/delivered offers
- Fulfillment of inactive offers
- Cancellation of non-active offers

### System State Failures
- Orders when all boxes are ordered/delivered
- Capacity calculations with mixed box statuses
- Notification cleanup for old vs recent offers

## Test Philosophy

Tests focus on:
1. **Business logic validation** - Core rules and constraints
2. **State transitions** - Status changes and their effects  
3. **Edge cases** - Boundary conditions and error scenarios
4. **Data integrity** - Calculations and inventory management

Each test is minimal, focused, and tests one specific behavior or failure mode.