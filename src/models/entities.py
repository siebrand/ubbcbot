import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum


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


class AuthorizationStatus(Enum):
    UNAUTHORIZED = "unauthorized"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class Supplier:
    supplier_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    full_name: str | None = None
    contact_email: str | None = None
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Offer:
    offer_id: int = 0
    supplier_name: str = ""
    name: str = ""
    description: str = ""
    images: list = field(default_factory=list)
    price_per_unit: Decimal = Decimal("0.0")
    wholesale_box_size: int = 12
    max_quantity: int | None = None
    status: str = OfferStatus.DRAFT.value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Customer:
    customer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    telegram_user_id: int = 0  # -1 for guest users
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language: str = "nl"  # Default to Dutch
    location: str = "Venster, Berlijnplein 520, Utrecht"
    authorization_status: str = AuthorizationStatus.UNAUTHORIZED.value
    subscribed_to_offers: bool = False
    is_guest: bool = False
    contact_info: str | None = None
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
    unit_price: Decimal = Decimal("0.0")
    total_price: Decimal = Decimal("0.0")
    status: str = OrderStatus.PENDING.value
    placed_by_admin: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    update_date: datetime | None = field(default_factory=lambda: datetime.now(UTC))


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
    """Analytics event for purchase reporting.

    Only two event types are recorded:
      - ORDER_CREATED:    an order was placed (answers "when do customers buy")
      - PAYMENT_RECEIVED: an order was paid (answers "top customers by spend")

    No personal data is stored here: the customer is referenced only by the
    pseudonymous ``customer_id``. Reporting resolves the real name at report
    time by looking the id up in the customers table, so right-to-be-forgotten
    is handled entirely on the customers record.

    The ``event-time-index`` GSI (hash ``event_type``, range ``changed_at``)
    serves both queries directly from the real attributes, so no composite key
    fields are needed.
    """

    history_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str = ""  # Pseudonymous reference; name resolved from customers table
    offer_name: str = ""  # Denormalized product name (not personal data)
    event_type: str = ""  # ORDER_CREATED | PAYMENT_RECEIVED
    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    amount: Decimal | None = None  # Euro value: ordered value (CREATED) / paid value (PAYMENT_RECEIVED)

    # TTL (5 years prod, 90 days test)
    ttl: int | None = None

    def __post_init__(self):
        if not self.ttl:
            import os
            from datetime import timedelta

            environment = os.environ.get("ENVIRONMENT", "test")
            ttl_days = 1825 if environment == "prod" else 90  # 5 years prod, 90 days test
            expiry = self.changed_at + timedelta(days=ttl_days)
            self.ttl = int(expiry.timestamp())


@dataclass
class CustomerCredit:
    customer_id: str = ""  # Primary key
    current_balance: Decimal = Decimal("0.0")
    total_credits_issued: Decimal = Decimal("0.0")
    total_credits_used: Decimal = Decimal("0.0")
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CreditTransaction:
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str = ""
    transaction_type: str = ""  # CREDIT_ISSUED, ADJUSTMENT, APPLIED, MANUAL_ADD, MANUAL_SUBTRACT
    amount: Decimal = Decimal("0.0")  # Positive for credits, negative for usage
    balance_before: Decimal = Decimal("0.0")
    balance_after: Decimal = Decimal("0.0")
    reason: str = ""
    created_by: int = 0  # Admin user ID
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
