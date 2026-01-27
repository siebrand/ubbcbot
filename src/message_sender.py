"""
Unified message sender for bot and admin user messages
Handles async sending to avoid Lambda timeouts
"""
import os
import json
import asyncio
import logging
import boto3
import requests
from services.database import DynamoDBService
from services.user_client import UserClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level event loop for Lambda container reuse
_loop = None
_user_client = None

def get_event_loop():
    """Get or create event loop for Lambda container"""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop

def lambda_handler(event, context):
    """
    Send messages from bot or admin account
    
    Event format:
    {
        "messages": [
            {
                "user_id": 123456789,
                "message": "Text",
                "from_admin": true/false,
                "parse_mode": "HTML" (optional),
                "disable_web_page_preview": true (optional)
            }
        ],
        "environment": "test"
    }
    """
    try:
        messages = event.get('messages', [])
        environment = event.get('environment', 'test')
        
        if not messages:
            return {'statusCode': 400, 'body': json.dumps({'error': 'No messages provided'})}
        
        # Get credentials
        ssm = boto3.client('ssm')
        bot_token = ssm.get_parameter(
            Name=f'/ubbc-bot/{environment}/telegram-bot-token',
            WithDecryption=True
        )['Parameter']['Value']
        
        # Send messages
        loop = get_event_loop()
        results = loop.run_until_complete(send_messages(messages, environment, bot_token))
        
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
        error_count = len(results) - success_count
        
        logger.info(f"Sent {success_count} messages, {error_count} errors out of {len(messages)} total")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success_count': success_count,
                'error_count': error_count,
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"Error in message sender: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}

async def send_messages(messages, environment, bot_token):
    """Send all messages with controlled concurrency"""
    # Separate admin and bot messages
    admin_messages = [msg for msg in messages if msg.get('from_admin')]
    bot_messages = [msg for msg in messages if not msg.get('from_admin')]
    
    results = []
    
    # Send admin messages with limited concurrency (max 5 at a time)
    if admin_messages:
        logger.info(f"Sending {len(admin_messages)} admin messages with concurrency limit")
        for i in range(0, len(admin_messages), 5):
            batch = admin_messages[i:i+5]
            tasks = [send_from_admin(msg, environment) for msg in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            results.extend(batch_results)
            logger.info(f"Completed batch {i//5 + 1}, sent {len([r for r in batch_results if isinstance(r, dict) and r.get('success')])} messages")
    
    # Send bot messages concurrently (faster, no connection overhead)
    if bot_messages:
        logger.info(f"Sending {len(bot_messages)} bot messages")
        tasks = [send_from_bot(msg, environment, bot_token) for msg in bot_messages]
        bot_results = await asyncio.gather(*tasks, return_exceptions=True)
        results.extend(bot_results)
    
    # Notify admin of failures
    failures = [r for r in results if isinstance(r, dict) and not r.get('success')]
    if failures:
        await notify_admin_of_failures(failures, environment, bot_token)
    
    return results

async def send_from_admin(msg, environment):
    """Send message from admin account via Telethon"""
    global _user_client
    
    try:
        if _user_client is None:
            _user_client = UserClient()
        
        user_id = msg['user_id']
        message = msg['message']
        parse_mode = msg.get('parse_mode')
        disable_web_page_preview = msg.get('disable_web_page_preview', False)
        
        # Add TEST prefix in test environment
        if environment == 'test':
            message = f"TEST - {message}"
        
        await _user_client.send_message(user_id, message, parse_mode, disable_web_page_preview)
        
        return {'success': True, 'user_id': user_id}
    except Exception as e:
        logger.error(f"Error sending from admin to {msg.get('user_id')}: {e}")
        return {'success': False, 'user_id': msg.get('user_id'), 'error': str(e), 'customer_name': msg.get('customer_name')}

async def send_from_bot(msg, environment, bot_token):
    """Send message from bot account"""
    try:
        user_id = msg['user_id']
        message = msg['message']
        parse_mode = msg.get('parse_mode')
        disable_web_page_preview = msg.get('disable_web_page_preview', False)
        
        # Add TEST prefix in test environment
        if environment == 'test':
            message = f"TEST - {message}"
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': user_id,
            'text': message
        }
        
        if parse_mode:
            payload['parse_mode'] = parse_mode
        if disable_web_page_preview:
            payload['disable_web_page_preview'] = True
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.post(url, json=payload))
        
        if response.status_code == 200:
            return {'success': True, 'user_id': user_id}
        else:
            return {'success': False, 'user_id': user_id, 'error': response.text, 'customer_name': msg.get('customer_name')}
            
    except Exception as e:
        logger.error(f"Error sending from bot to {msg.get('user_id')}: {e}")
        return {'success': False, 'user_id': msg.get('user_id'), 'error': str(e), 'customer_name': msg.get('customer_name')}

async def notify_admin_of_failures(failures, environment, bot_token):
    """Notify admin of failed message deliveries"""
    try:
        admin_user_id = int(os.environ.get('ADMIN_USER_ID', '15005473'))
        
        message = "⚠️ Failed to send messages:\n\n"
        for failure in failures:
            customer_name = failure.get('customer_name', 'Unknown')
            user_id = failure.get('user_id', 'Unknown')
            error = failure.get('error', 'Unknown error')[:100]
            message += f"• {customer_name} (ID: {user_id})\n  Error: {error}\n\n"
        
        if environment == 'test':
            message = f"TEST - {message}"
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {'chat_id': admin_user_id, 'text': message}
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: requests.post(url, json=payload))
        
    except Exception as e:
        logger.error(f"Failed to notify admin of failures: {e}")
