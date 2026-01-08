from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional, Dict, Any
from enum import Enum
from decimal import Decimal
import uuid

class OfferStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ORDERED = "ordered"
    SOLD_OUT = "sold_out"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    INACTIVE = "inactive"

class BoxStatus(Enum):
    OPEN = "open"
    FULL = "full"
    ORDERED = "ordered"
    DELIVERED = "delivered"

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    RECEIVED_PARTIAL_DELAYED = "received_partial_delayed"
    CANCELLED_UNAVAILABLE = "cancelled_unavailable"
    READY_FOR_LABELING = "ready_for_labeling"
    LABELING_COMPLETED = "labeling_completed"
    AWAITING_PAYMENT = "awaiting_payment"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class DeliveryAction(Enum):
    FULL = "full"
    DELAYED = "delayed"
    CANCEL = "cancel"
    INCOMPLETE = "incomplete"

class DiscountStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class AuthorizationStatus(Enum):
    UNAUTHORIZED = "unauthorized"
    APPROVED = "approved"
    REJECTED = "rejected"

@dataclass
class Supplier:
    supplier_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    full_name: Optional[str] = None
    contact_email: Optional[str] = None
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class Offer:
    offer_id: int = 0
    supplier_name: str = ""
    name: str = ""
    description: str = ""
    images: list = field(default_factory=list)
    price_per_unit: Decimal = Decimal('0.0')
    wholesale_box_size: int = 12
    max_quantity: Optional[int] = None
    status: str = OfferStatus.DRAFT.value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class Customer:
    customer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    telegram_user_id: int = 0  # -1 for guest users
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: str = "nl"  # Default to Dutch
    location: str = "Venster, Berlijnplein 520, Utrecht"
    authorization_status: str = AuthorizationStatus.UNAUTHORIZED.value
    subscribed_to_offers: bool = False
    is_guest: bool = False
    contact_info: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class Box:
    box_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    offer_id: int = 0
    current_quantity: int = 0
    max_capacity: int = 12
    status: str = BoxStatus.OPEN.value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class Order:
    order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str = ""
    box_id: str = ""
    offer_id: int = 0
    quantity: int = 1
    received_quantity: int = 0
    unit_price: Decimal = Decimal('0.0')
    total_price: Decimal = Decimal('0.0')
    status: str = OrderStatus.PENDING.value
    placed_by_admin: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    update_date: Optional[datetime] = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class DiscountPeriod:
    discount_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    discount_percentage: Decimal = Decimal('0.0')
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: Optional[datetime] = None
    status: str = DiscountStatus.ACTIVE.value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class EditContext:
    context_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chat_id: int = 0
    edit_type: str = ""
    entity_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class NotificationMessage:
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    offer_id: int = 0
    chat_id: int = 0
    message_id: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
