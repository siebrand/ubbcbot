from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import uuid

class OfferStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    COMPLETED = "completed"
    DELIVERED = "delivered"

class BoxStatus(Enum):
    OPEN = "open"
    MINIMUM_REACHED = "minimum_reached"
    FULL = "full"
    ORDERED = "ordered"
    DELIVERED = "delivered"

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    DELIVERED = "delivered"

class DiscountStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

@dataclass
class Supplier:
    supplier_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    contact_email: Optional[str] = None
    status: str = "active"
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Offer:
    offer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    supplier_name: str = ""
    name: str = ""
    description: str = ""
    price_per_unit: float = 0.0
    wholesale_box_size: int = 12
    min_quantity_breakeven: int = 10
    max_quantity: Optional[int] = None
    status: str = OfferStatus.ACTIVE.value
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Customer:
    customer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    telegram_user_id: int = 0
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Box:
    box_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    offer_id: str = ""
    current_quantity: int = 0
    max_capacity: int = 12
    min_breakeven: int = 10
    status: str = BoxStatus.OPEN.value
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Order:
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str = ""
    box_id: str = ""
    offer_id: str = ""
    quantity: int = 1
    unit_price: float = 0.0
    total_price: float = 0.0
    status: str = OrderStatus.PENDING.value
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class DiscountPeriod:
    discount_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    discount_percentage: float = 0.0
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    status: str = DiscountStatus.ACTIVE.value
    created_at: datetime = field(default_factory=datetime.utcnow)