"""The real handler classes behind the keys of the handlers dict, for tests that must not accept a made-up method."""

from handlers.admin.admin_commands import AdminCommandsHandler
from handlers.admin.credit_commands import CreditCommands
from handlers.admin.delivery_overview_handler import DeliveryOverviewHandler
from handlers.admin.import_handler import ImportHandler
from handlers.admin.labeling_commands import LabelingCommands
from handlers.admin.offer_commands import OfferCommands
from handlers.admin.order_commands import AdminOrderCommands
from handlers.admin.supplier_commands import SupplierCommands
from handlers.admin.test_commands import TestCommands as SetupDataCommands
from handlers.admin.user_commands import UserCommands
from handlers.admin.wholesale_delivery_commands import WholesaleDeliveryCommands
from handlers.customer.auth_commands import AuthCommands
from handlers.customer.changelog_commands import ChangelogCommands
from handlers.customer.credit_commands import CustomerCreditCommands
from handlers.customer.data_export_commands import DataExportCommands
from handlers.customer.info_commands import InfoCommands
from handlers.customer.order_commands import CustomerOrderCommands

HANDLER_CLASSES = {
    "admin_commands": AdminCommandsHandler,
    "admin_order": AdminOrderCommands,
    "auth": AuthCommands,
    "changelog": ChangelogCommands,
    "credit": CreditCommands,
    "customer_credit": CustomerCreditCommands,
    "customer_order": CustomerOrderCommands,
    "data_export": DataExportCommands,
    "delivery_overview": DeliveryOverviewHandler,
    "import": ImportHandler,
    "info": InfoCommands,
    "labeling": LabelingCommands,
    "offer": OfferCommands,
    "supplier": SupplierCommands,
    "test": SetupDataCommands,
    "user": UserCommands,
    "wholesale_delivery": WholesaleDeliveryCommands,
}

# Attributes that a handler sets in __init__ (so they are not on the class) and that the routes use
INSTANCE_ATTRIBUTES = {"admin_order": ["viewing", "editing", "cancellation", "placement", "status_mgmt", "maintenance"]}


def handler_mock_spec(key: str) -> list[str]:
    """The names a mock of the handler `key` may have: those of the real class, and nothing made up"""
    return dir(HANDLER_CLASSES[key]) + INSTANCE_ATTRIBUTES.get(key, [])
