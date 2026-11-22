from .boxes import BoxManagementHandler
from .creation import OfferCreationHandler
from .editing import OfferEditingHandler
from .instant import InstantOrderHandler
from .management import OfferManagementHandler
from .notifications import NotificationHandler
from .overview import OfferOverviewHandler


class OfferCommands(
    OfferCreationHandler,
    OfferManagementHandler,
    OfferOverviewHandler,
    OfferEditingHandler,
    BoxManagementHandler,
    InstantOrderHandler,  # before NotificationHandler, its base
    NotificationHandler,
):
    """Main offer commands handler that combines all offer-related functionality"""

    pass
