#!/usr/bin/env python3
"""
Setup script to authenticate admin Telegram account with Telethon
Run this locally to generate session string and store in Parameter Store
"""

import asyncio
import getpass
import sys

import boto3
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_user_client.py [test|prod]")
        sys.exit(1)

    environment = sys.argv[1]
    if environment not in ["test", "prod"]:
        print("Environment must be 'test' or 'prod'")
        sys.exit(1)

    ssm = boto3.client("ssm")

    # Get API credentials
    print("\nYou need Telegram API credentials from https://my.telegram.org/apps")
    api_id = input("Enter API ID: ").strip()
    api_hash = getpass.getpass("Enter API Hash: ")

    # Store API credentials
    ssm.put_parameter(
        Name=f"/ubbc-bot/{environment}/telegram-api-id", Value=api_id, Type="SecureString", Overwrite=True
    )
    ssm.put_parameter(
        Name=f"/ubbc-bot/{environment}/telegram-api-hash", Value=api_hash, Type="SecureString", Overwrite=True
    )
    print("✓ Stored API credentials in Parameter Store")

    # Authenticate and create session
    print("\nAuthenticating your admin account...")
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("Enter your phone number (with country code): ").strip()
        await client.send_code_request(phone)
        code = getpass.getpass("Enter the code you received: ")
        try:
            await client.sign_in(phone, code)
        except Exception as e:
            if "SessionPasswordNeededError" in str(type(e).__name__):
                password = getpass.getpass("Two-step verification enabled. Enter your password: ")
                await client.sign_in(password=password)
            else:
                raise

    # Save session string
    session_string = client.session.save()
    ssm.put_parameter(
        Name=f"/ubbc-bot/{environment}/telegram-session", Value=session_string, Type="SecureString", Overwrite=True
    )
    print("✓ Stored session in Parameter Store")

    print(f"\n✓ Setup complete for {environment} environment")
    print("You can now send messages from your admin account via Lambda")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
