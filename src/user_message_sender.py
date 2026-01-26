"""
Lambda handler for sending messages from admin user account
"""
import os
import json
import asyncio
from services.user_client import UserClient

def lambda_handler(event, context):
    """
    Send message from admin account to user
    
    Event format:
    {
        "user_id": 123456789,
        "message": "Payment reminder text"
    }
    """
    try:
        user_id = event['user_id']
        message = event['message']
        
        # Add TEST prefix in test environment
        environment = os.environ.get('ENVIRONMENT', 'test')
        if environment == 'test':
            message = f"TEST - {message}"
        
        # Run async send
        asyncio.run(send_message(user_id, message))
        
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

async def send_message(user_id: int, message: str):
    """Send message via user client"""
    client = UserClient()
    await client.send_message(user_id, message)
