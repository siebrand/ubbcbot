"""
Telethon user client for sending messages from admin account
"""
import os
import boto3
from telethon import TelegramClient
from telethon.sessions import StringSession

# Module-level cache for Lambda container reuse
_client = None
_credentials = None

class UserClient:
    def __init__(self):
        self.ssm = boto3.client('ssm')
        self.environment = os.environ.get('ENVIRONMENT', 'test')
        
    async def get_client(self):
        """Get or create authenticated Telethon client"""
        global _client, _credentials
        
        if _client and _client.is_connected():
            return _client
            
        # Get credentials from cache or Parameter Store
        if not _credentials:
            _credentials = self._get_credentials()
            
        # Create client with session
        _client = TelegramClient(
            StringSession(_credentials['session']) if _credentials['session'] else StringSession(),
            int(_credentials['api_id']),
            _credentials['api_hash']
        )
        
        await _client.connect()
        
        if not await _client.is_user_authorized():
            raise Exception("User client not authorized. Run setup script to authenticate.")
            
        return _client
    
    async def send_message(self, user_id: int, message: str, parse_mode: str = None, disable_web_page_preview: bool = False):
        """Send message from admin account to user"""
        client = await self.get_client()
        
        # Get entity to ensure user is resolved (needed when session cache is empty)
        try:
            entity = await client.get_entity(user_id)
        except Exception as e:
            # If get_entity fails, try sending directly (might work if user is cached)
            pass
        
        await client.send_message(
            user_id, 
            message,
            parse_mode=parse_mode,
            link_preview=not disable_web_page_preview
        )
    
    def _get_credentials(self):
        """Get all credentials in a single batch call"""
        parameter_names = [
            f'/ubbc-bot/{self.environment}/telegram-api-id',
            f'/ubbc-bot/{self.environment}/telegram-api-hash',
            f'/ubbc-bot/{self.environment}/telegram-session'
        ]
        
        try:
            response = self.ssm.get_parameters(
                Names=parameter_names,
                WithDecryption=True
            )
            
            params = {p['Name'].split('/')[-1]: p['Value'] for p in response['Parameters']}
            
            return {
                'api_id': params.get('telegram-api-id'),
                'api_hash': params.get('telegram-api-hash'),
                'session': params.get('telegram-session')
            }
        except Exception as e:
            raise Exception(f"Failed to retrieve credentials from Parameter Store: {e}")
