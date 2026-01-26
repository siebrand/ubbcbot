"""
Telethon user client for sending messages from admin account
"""
import os
import boto3
from telethon import TelegramClient
from telethon.sessions import StringSession

class UserClient:
    def __init__(self):
        self.ssm = boto3.client('ssm')
        self.environment = os.environ.get('ENVIRONMENT', 'test')
        self.client = None
        
    async def get_client(self):
        """Get or create authenticated Telethon client"""
        if self.client and self.client.is_connected():
            return self.client
            
        # Get credentials from Parameter Store
        api_id = self._get_parameter(f'/ubbc-bot/{self.environment}/telegram-api-id')
        api_hash = self._get_parameter(f'/ubbc-bot/{self.environment}/telegram-api-hash')
        session_string = self._get_parameter(f'/ubbc-bot/{self.environment}/telegram-session', required=False)
        
        # Create client with session
        self.client = TelegramClient(
            StringSession(session_string) if session_string else StringSession(),
            int(api_id),
            api_hash
        )
        
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            raise Exception("User client not authorized. Run setup script to authenticate.")
            
        return self.client
    
    async def send_message(self, user_id: int, message: str):
        """Send message from admin account to user"""
        client = await self.get_client()
        await client.send_message(user_id, message)
    
    def _get_parameter(self, name: str, required: bool = True):
        """Get parameter from Parameter Store"""
        try:
            response = self.ssm.get_parameter(Name=name, WithDecryption=True)
            return response['Parameter']['Value']
        except self.ssm.exceptions.ParameterNotFound:
            if required:
                raise Exception(f"Required parameter {name} not found in Parameter Store")
            return None
