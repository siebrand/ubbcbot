"""
Lambda handler for sending messages from admin user account
"""
import os
import json
import asyncio
from services.user_client import UserClient

# Module-level event loop for Lambda container reuse
_loop = None

def get_event_loop():
    """Get or create event loop for Lambda container"""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop

def lambda_handler(event, context):
    """
    Send message from admin account to user
    
    Event format:
    {
        "user_id": 123456789,
        "message": "Payment reminder text",
        "parse_mode": "HTML" (optional),
        "disable_web_page_preview": true (optional)
    }
    """
    try:
        user_id = event['user_id']
        message = event['message']
        parse_mode = event.get('parse_mode')
        disable_web_page_preview = event.get('disable_web_page_preview', False)
        
        # Add TEST prefix in test environment
        environment = os.environ.get('ENVIRONMENT', 'test')
        if environment == 'test':
            message = f"TEST - {message}"
        
        # Run async send with persistent event loop
        loop = get_event_loop()
        loop.run_until_complete(send_message(user_id, message, parse_mode, disable_web_page_preview))
        
        return {
            'statusCode': 200,
            'body': json.dumps({'success': True})
        }
    except Exception as e:
        print(f"Error sending user message: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

async def send_message(user_id: int, message: str, parse_mode: str = None, disable_web_page_preview: bool = False):
    """Send message via user client"""
    client = UserClient()
    await client.send_message(user_id, message, parse_mode, disable_web_page_preview)
