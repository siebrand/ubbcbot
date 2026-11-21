from .boxes import BoxManagementHandler
from .creation import OfferCreationHandler
from .editing import OfferEditingHandler
from .instant import InstantOrderHandler
from .management import OfferManagementHandler
from .notifications import NotificationHandler


class OfferCommands(
    OfferCreationHandler,
    OfferManagementHandler,
    OfferEditingHandler,
    BoxManagementHandler,
    NotificationHandler,
    InstantOrderHandler,
):
    """Main offer commands handler that combines all offer-related functionality"""

    pass
