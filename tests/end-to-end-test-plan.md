# UBBC Bot End-to-End Test Plan: Happy Path

## Prerequisites
- Bot deployed in test environment
- Admin user ID: 15005473
- Test customer registered and approved

## Test Scenario
- 2 offers with different box sizes
- Single customer orders enough to fill one complete box
- Full workflow from creation to payment confirmation

---

## Phase 1: Setup Test Data

### 1.1 Setup Test Environment
```
/setup_test_data
```

### 1.2 Verify Initial State
```
/list_offers
/list_suppliers
/box_status
```

---

## Phase 2: Create First Offer (12-unit box)

### 2.1 Create Draft Offer
```
/create_offer TestBrewery "IPA Special Edition" 8.50 12
```

### 2.2 Add Description and Publish
```
/offer_details 1 edit
```
*Click "Edit Description" button, then type:*
```
Premium IPA with citrus notes and floral aroma. Limited edition batch from TestBrewery.
```

### 2.3 Publish Offer
```
/publish_offer 1
```

---

## Phase 3: Create Second Offer (6-unit box)

### 3.1 Create Draft Offer
```
/create_offer CraftCo "Stout Deluxe" 12.00 6
```

### 3.2 Add Description and Publish
```
/offer_details 2 edit
```
*Click "Edit Description" button, then type:*
```
Rich chocolate stout with coffee undertones. Perfect for cold evenings.
```

### 3.3 Publish Offer
```
/publish_offer 2
```

---

## Phase 4: Customer Orders (Fill First Box)

### 4.1 Customer Views Offers
```
/list_offers
```

### 4.2 Customer Places Orders (Total: 12 units for Offer 1)
```
/order 1 5
/order 1 4
/order 1 3
```

### 4.3 Verify Box Status
```
/box_status
```
*Expected: First offer box should show FULL status*

---

## Phase 5: Fulfillment Process

### 5.1 Admin Fulfills Offer
```
/fulfill_offer 1
```
*Click "Fulfill with 1 boxes" button*

### 5.2 Verify Order Status
```
/all_orders ordered
```

---

## Phase 6: Wholesale Delivery Processing

### 6.1 Start Wholesale Delivery
```
/wholesale_delivery
```

### 6.2 Select Supplier and Offer
*Follow prompts:*
1. Click "TestBrewery" button
2. Click offer button for "IPA Special Edition"
3. Click box button for the full box

### 6.3 Process Full Delivery
*Click "Full Delivery" button*

---

## Phase 7: Delivery Overview and Payment

### 7.1 Send Delivery Overviews
```
/send_overviews
```

### 7.2 Provide Payment Link
*When prompted, enter:*
```
https://payment.example.com/ubbc-test-batch-1
```

### 7.3 Mark Customer as Paid
```
/mark_paid
```
*Click the customer's "Mark Paid" button*

---

## Phase 8: Verification Commands

### 8.1 Verify Final States
```
/all_orders completed
/box_status
/list_offers
```

### 8.2 Customer Verification
```
/my_orders
```

---

## Expected Results

### After Phase 2:
- Offer 1 created with ACTIVE status
- Box created with 1/12 capacity (admin auto-order)

### After Phase 3:
- Offer 2 created with ACTIVE status
- Box created with 1/6 capacity (admin auto-order)

### After Phase 4:
- Offer 1 box: FULL status (12/12 units)
- Customer has 3 pending orders totaling 12 units

### After Phase 5:
- All customer orders status: ORDERED
- Box status: ORDERED

### After Phase 6:
- All orders status: READY_FOR_LABELING

### After Phase 7:
- All orders status: COMPLETED
- Customer receives payment confirmation

### Final Verification:
- Customer orders show COMPLETED status
- Box shows DELIVERED status
- Offer 1 shows COMPLETED status
- Offer 2 remains ACTIVE with 1/6 capacity

---

## Test Data Summary

**Offer 1**: IPA Special Edition - €8.50 - 12 units box
**Offer 2**: Stout Deluxe - €12.00 - 6 units box
**Customer Orders**: 12 units total (5+4+3) for Offer 1
**Total Value**: €102.00 (12 × €8.50)
**Payment Link**: https://payment.example.com/ubbc-test-batch-1

This test plan covers the complete happy path workflow from offer creation through payment confirmation, testing all major system components and status transitions.