from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional
from enum import Enum
from decimal import Decimal
import uuid

class OfferStatus(Enum):
    DRAFT = "draft"
    IMPORT = "import"
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
    ORDERED = "ordered"
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

@dataclass
class OrderHistory:
    history_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str = ""
    customer_id: str = ""  # Denormalized for reporting
    customer_name: str = ""  # Denormalized - customer may be deleted
    offer_name: str = ""  # Denormalized - offer may be deleted
    event_type: str = ""  # ORDER_CREATED, ORDER_CANCELLED, PRICE_CHANGED, STATUS_CHANGED, PAYMENT_RECEIVED
    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    changed_by: int = 0  # Admin user ID (0 for system)
    field_name: str = ""  # Field that changed
    old_value: str = ""
    new_value: str = ""
    reason: str = ""
    amount: Optional[Decimal] = None  # Payment/refund amount for financial events
    
    # Composite fields for GSI queries
    customer_event: str = ""  # Format: "customer_id#event_type" for customer-event-index
    event_date: str = ""  # Format: "event_type#2024-01-15T10:30:00Z" for event-date-index
    customer_name_event: str = ""  # Format: "customer_name#event_type" for customer-name-event-index
    
    # TTL (5 years prod, 90 days test)
    ttl: Optional[int] = None
    
    def __post_init__(self):
        # Auto-generate composite fields
        if self.customer_id and self.event_type:
            self.customer_event = f"{self.customer_id}#{self.event_type}"
        if self.event_type and self.changed_at:
            self.event_date = f"{self.event_type}#{self.changed_at.isoformat()}"
        if self.customer_name and self.event_type:
            self.customer_name_event = f"{self.customer_name}#{self.event_type}"
        # Set TTL based on environment
        if not self.ttl:
            import os
            from datetime import timedelta
            environment = os.environ.get('ENVIRONMENT', 'test')
            ttl_days = 1825 if environment == 'prod' else 90  # 5 years prod, 90 days test
            expiry = self.changed_at + timedelta(days=ttl_days)
            self.ttl = int(expiry.timestamp())

@dataclass
class CustomerCredit:
    customer_id: str = ""  # Primary key
    current_balance: Decimal = Decimal('0.0')
    total_credits_issued: Decimal = Decimal('0.0')
    total_credits_used: Decimal = Decimal('0.0')
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class CreditTransaction:
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str = ""
    transaction_type: str = ""  # CREDIT_ISSUED, ADJUSTMENT, APPLIED, MANUAL_ADD, MANUAL_SUBTRACT
    amount: Decimal = Decimal('0.0')  # Positive for credits, negative for usage
    balance_before: Decimal = Decimal('0.0')
    balance_after: Decimal = Decimal('0.0')
    reason: str = ""
    created_by: int = 0  # Admin user ID
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
