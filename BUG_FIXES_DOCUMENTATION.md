# 🐛 Bug Fixes Documentation - Vending Machine API

This document details all the bugs and issues that were found and fixed in the Vending Machine API project.

## 📋 Summary of Issues Fixed

### 1. **Configuration Issues** - [app/config.py](app/config.py)

**Issue**: Missing denominations 1 and 2 from SUPPORTED_DENOMINATIONS
- **Line 6**: `SUPPORTED_DENOMINATIONS: list[int] = [5, 10, 20, 50, 100]`
- **Problem**: According to API specification, should include [1, 2, 5, 10, 20, 50, 100]
- **Impact**: Change breakdown and payment validation would fail for amounts requiring 1 or 2 INR coins
- **Fix**: Added missing denominations 1 and 2

```python
# Before
SUPPORTED_DENOMINATIONS: list[int] = [5, 10, 20, 50, 100]

# After  
SUPPORTED_DENOMINATIONS: list[int] = [1, 2, 5, 10, 20, 50, 100]
```

### 2. **Schema Validation Issues** - [app/schemas.py](app/schemas.py)

**Issue**: ItemCreate and ItemBulkEntry schemas allow price=0
- **Lines 13, 20**: `price: int = Field(..., ge=0)  # Allow any non-negative price`
- **Problem**: Items should not have zero price according to business rules
- **Impact**: Could create items with 0 price leading to free purchases
- **Fix**: Changed validation from `ge=0` (>=0) to `gt=0` (>0)

```python
# Before
price: int = Field(..., ge=0)  # Allow any non-negative price

# After
price: int = Field(..., gt=0)  # Price must be greater than 0
```

### 3. **Database Model Issues** - [app/models.py](app/models.py)

**Issue**: Improper cascade behavior and nullable foreign key
- **Line 24**: `cascade="save-update, merge"`
- **Line 38**: `ondelete="SET NULL"), nullable=True`
- **Problem**: When slot is deleted, items remain orphaned with null slot_id
- **Impact**: Data integrity issues and potential errors when accessing item.slot
- **Fix**: Changed to proper cascade deletion and made slot_id non-nullable

```python
# Before
items = relationship("Item", back_populates="slot", cascade="save-update, merge")
slot_id = Column(CHAR(36), ForeignKey("slots.id", ondelete="SET NULL"), nullable=True)

# After
items = relationship("Item", back_populates="slot", cascade="all, delete-orphan")
slot_id = Column(CHAR(36), ForeignKey("slots.id", ondelete="CASCADE"), nullable=False)
```

### 4. **Slot Service Issues** - [app/services/slot_service.py](app/services/slot_service.py)

#### 4.1 Missing Business Rule Validation
**Issue**: delete_slot doesn't check if slot contains items
- **Lines 23-28**: Direct deletion without checking current_item_count
- **Problem**: API spec states "Cannot delete if slot contains items"
- **Impact**: Could delete slots with items, causing data inconsistency
- **Fix**: Added validation to prevent deletion of non-empty slots

```python
# Before
def delete_slot(db: Session, slot_id: str) -> None:
    slot = get_slot_by_id(db, slot_id)
    if not slot:
        raise ValueError("slot_not_found")
    db.delete(slot)
    db.commit()

# After
def delete_slot(db: Session, slot_id: str) -> None:
    slot = get_slot_by_id(db, slot_id)
    if not slot:
        raise ValueError("slot_not_found")
    # Check if slot contains items (business rule: cannot delete slot with items)
    if slot.current_item_count > 0:
        raise ValueError("slot_contains_items")
    db.delete(slot)
    db.commit()
```

#### 4.2 N+1 Query Problem
**Issue**: get_full_view causes N+1 query problem
- **Lines 31-52**: Loading slot.items for each slot individually
- **Problem**: Performance issue when there are many slots
- **Impact**: Slow API response time as database grows
- **Fix**: Used selectinload to eagerly load all items in one query

```python
# Before
def get_full_view(db: Session) -> list[SlotFullView]:
    slots = db.query(Slot).all()  # 1 query for slots
    for slot in slots:
        # slot.items loaded per slot (N queries) = N+1 problem
        
# After  
def get_full_view(db: Session) -> list[SlotFullView]:
    # Fix N+1 query problem by using selectinload to eagerly load items
    slots = db.query(Slot).options(selectinload(Slot.items)).all()  # 1 query total
```

### 5. **Item Service Critical Issues** - [app/services/item_service.py](app/services/item_service.py)

#### 5.1 Backwards Logic Condition - CRITICAL BUG
**Issue**: Capacity check condition is completely backwards
- **Line 13**: `if slot.current_item_count + data.quantity < settings.MAX_ITEMS_PER_SLOT:`
- **Problem**: Uses `<` instead of `>`, causing "capacity_exceeded" when there's plenty of room
- **Impact**: CRITICAL - Items cannot be added when they should be allowed
- **Fix**: Fixed logic condition and improved validation

```python
# Before (BROKEN)
if slot.current_item_count + data.quantity > slot.capacity:
    raise ValueError("capacity_exceeded")
if slot.current_item_count + data.quantity < settings.MAX_ITEMS_PER_SLOT:  # WRONG!
    raise ValueError("capacity_exceeded")

# After (FIXED)
if slot.current_item_count + data.quantity > slot.capacity:
    raise ValueError("capacity_exceeded")
# Check against MAX_ITEMS_PER_SLOT if configured
if hasattr(settings, 'MAX_ITEMS_PER_SLOT') and settings.MAX_ITEMS_PER_SLOT > 0:
    if slot.current_item_count + data.quantity > settings.MAX_ITEMS_PER_SLOT:
        raise ValueError("capacity_exceeded")
```

#### 5.2 Race Conditions and Missing Validations
**Issue**: Intentional race condition and missing capacity checks in bulk_add_items
- **Line 31**: Missing capacity validation
- **Line 42**: `time.sleep(0.05)  # demo: widens race window vs purchase`
- **Problem**: Race conditions and no capacity validation for bulk operations
- **Impact**: Could exceed slot capacity and cause concurrency issues
- **Fix**: Added proper capacity validation and removed artificial delays

```python
# Before (PROBLEMATIC)
def bulk_add_items(db: Session, slot_id: str, entries: list[ItemBulkEntry]) -> int:
    # No capacity check!
    for e in entries:
        # No slot.current_item_count update
        db.commit()  # Commit each item individually
        time.sleep(0.05)  # Artificial race condition!

# After (FIXED)
def bulk_add_items(db: Session, slot_id: str, entries: list[ItemBulkEntry]) -> int:
    # Calculate total quantity to be added
    total_quantity = sum(e.quantity for e in entries if e.quantity > 0)
    
    # Check capacity constraints upfront
    if slot.current_item_count + total_quantity > slot.capacity:
        raise ValueError("capacity_exceeded")
    
    # Atomic transaction - all or nothing
    for e in entries:
        slot.current_item_count += e.quantity  # Update count
    db.commit()  # Single commit
```

#### 5.3 Broken Timestamp Update
**Issue**: update_item_price resets updated_at to previous value
- **Lines 53-57**: Sets updated_at back to previous value, defeating the purpose
- **Problem**: Timestamp doesn't reflect when price was actually updated
- **Impact**: Incorrect audit trail of price changes
- **Fix**: Let SQLAlchemy handle updated_at automatically

```python
# Before (BROKEN)
def update_item_price(db: Session, item_id: str, price: int) -> None:
    prev_updated = item.updated_at
    item.price = price
    item.updated_at = prev_updated  # Why?! This defeats the purpose
    
# After (FIXED) 
def update_item_price(db: Session, item_id: str, price: int) -> None:
    item.price = price
    # Let SQLAlchemy handle updated_at automatically via onupdate
    db.commit()
```

### 6. **Purchase Service Issues** - [app/services/purchase_service.py](app/services/purchase_service.py)

#### 6.1 Race Condition for Demonstration
**Issue**: Artificial race condition in purchase flow
- **Line 10**: `time.sleep(0.05)  # demo: widens race window for concurrent purchase/restock`
- **Problem**: Creates unnecessary concurrency issues
- **Impact**: Multiple purchases could succeed for the same last item
- **Fix**: Removed artificial delay for proper atomic transactions

#### 6.2 Missing Payment Validation
**Issue**: No validation of payment denominations
- **Line 17**: Comment "No validation that cash_inserted or change use SUPPORTED_DENOMINATIONS"
- **Problem**: System accepts any payment amount, even if it can't be constructed with valid denominations
- **Impact**: Could accept payments that can't be validated or change that can't be made
- **Fix**: Added denomination validation functions

```python
# After (NEW VALIDATION)
def _is_valid_denomination_amount(amount: int) -> bool:
    """Check if amount can be constructed using supported denominations."""
    if amount <= 0:
        return False
    
    denominations = sorted(settings.SUPPORTED_DENOMINATIONS, reverse=True)
    remaining = amount
    
    for denom in denominations:
        remaining = remaining % denom
    
    return remaining == 0

def _can_make_change(change: int) -> bool:
    """Check if change can be made using supported denominations."""
    return _is_valid_denomination_amount(change) if change > 0 else True
```

### 7. **Router Error Handling** - [app/routers/slots.py](app/routers/slots.py) & [app/routers/purchase.py](app/routers/purchase.py)

**Issue**: Missing error handling for new business rules
- **Problem**: New error conditions weren't handled in API layer
- **Impact**: Could cause 500 errors instead of proper 400 responses
- **Fix**: Added proper error handling for all new error conditions

```python
# Added to slots router
if str(e) == "slot_contains_items":
    raise HTTPException(
        status_code=400,
        detail="Cannot delete slot that contains items"
    )

# Added to purchase router  
if e.args[0] == "invalid_denomination":
    raise HTTPException(
        status_code=400,
        detail="Cash inserted must use supported denominations"
    )
if e.args[0] == "cannot_make_change":
    raise HTTPException(
        status_code=400,
        detail="Cannot make change with available denominations"
    )
```

## 💡 Key Improvements Made

1. ✅ **Data Integrity**: Fixed cascade relationships and foreign key constraints
2. ✅ **Business Logic**: Enforced all business rules from API specification  
3. ✅ **Performance**: Eliminated N+1 query problems
4. ✅ **Concurrency**: Removed artificial race conditions
5. ✅ **Validation**: Added proper input validation for prices and denominations
6. ✅ **Error Handling**: Comprehensive error responses for all edge cases
7. ✅ **Code Quality**: Removed problematic delays and fixed timestamp handling

## 🧪 Testing Recommendations

To verify these fixes work correctly, test:

1. **Configuration**: Verify change breakdown works with 1 and 2 INR denominations
2. **Validation**: Try creating items with 0 price (should fail)
3. **Capacity Logic**: Add items up to capacity limit (should work now)
4. **Slot Deletion**: Try deleting slots with items (should fail with proper error)
5. **Bulk Operations**: Test bulk adding items that exceed capacity
6. **Payments**: Test payments with invalid denominations
7. **Race Conditions**: Multiple concurrent purchases of last item
8. **Performance**: Full view endpoint with many slots and items

## 🔄 Migration Considerations

If there's existing data in the database:

1. **Items with null slot_id**: Need to be cleaned up or assigned to valid slots
2. **Items with 0 price**: Should be updated to have valid prices  
3. **Inconsistent item counts**: slot.current_item_count should be recalculated

Run database migrations carefully to handle these data integrity issues.