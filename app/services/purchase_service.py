from sqlalchemy.orm import Session

from app.config import settings
from app.models import Item


def purchase(db: Session, item_id: str, cash_inserted: int) -> dict:
    # Validate cash_inserted uses supported denominations
    if not _is_valid_denomination_amount(cash_inserted):
        raise ValueError("invalid_denomination")
    
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise ValueError("item_not_found")
    
    if item.quantity <= 0:
        raise ValueError("out_of_stock")
    
    if cash_inserted < item.price:
        raise ValueError("insufficient_cash", item.price, cash_inserted)
    
    change = cash_inserted - item.price
    
    # Validate that change can be made with supported denominations
    if not _can_make_change(change):
        raise ValueError("cannot_make_change")
    
    # Perform the purchase transaction atomically
    item.quantity -= 1
    if item.slot:
        item.slot.current_item_count -= 1
    
    db.commit()
    db.refresh(item)
    
    return {
        "item": item.name,
        "price": item.price,
        "cash_inserted": cash_inserted,
        "change_returned": change,
        "remaining_quantity": item.quantity,
        "message": "Purchase successful",
    }


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


def change_breakdown(change: int) -> dict:
    denominations = sorted(settings.SUPPORTED_DENOMINATIONS, reverse=True)
    result: dict[str, int] = {}
    remaining = change
    for d in denominations:
        if remaining <= 0:
            break
        count = remaining // d
        if count > 0:
            result[str(d)] = count
            remaining -= count * d
    return {"change": change, "denominations": result}
