from typing import Dict, Any
from .creation import OfferCreationHandler
from .management import OfferManagementHandler
from .editing import OfferEditingHandler
from .boxes import BoxManagementHandler
from .notifications import NotificationHandler

class OfferCommands(
    OfferCreationHandler,
    OfferManagementHandler, 
    OfferEditingHandler,
    BoxManagementHandler,
    NotificationHandler
):
    """Main offer commands handler that combines all offer-related functionality"""
    pass
