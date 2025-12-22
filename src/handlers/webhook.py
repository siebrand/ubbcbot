import json
import os
import logging
from typing import Dict, Any
from services.bot_service import BotService
from utils.response import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for Telegram webhook"""
    try:
        # Parse webhook data
        body = json.loads(event.get('body', '{}'))
        
        # Initialize bot service
        bot_service = BotService()
        
        # Process update
        response = bot_service.process_update(body)
        
        return create_response(200, {'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return create_response(500, {'error': 'Internal server error'})