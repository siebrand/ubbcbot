#!/usr/bin/env python3
"""
Group Customer Analysis Script

This script compares registered customers with members of the default Telegram group to identify:
A) Customers not in the default group
B) Group members not registered as customers
C) With --show-unapproved: group members the bot has not approved
   (registered customers whose status is not "approved", plus unregistered members).
   The member list comes from the admin user account in Parameter Store, because the
   Bot API cannot list group members. If that fails, the script falls back to the
   members the Bot API can see.
"""

import os
import sys
from typing import Any

import boto3
import requests

# Add src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from models.entities import AuthorizationStatus
from services.database import DynamoDBService


class GroupCustomerAnalyzer:
    def __init__(self, environment: str = "test"):
        self.environment = environment
        # Set AWS region if not set
        if not os.environ.get("AWS_DEFAULT_REGION"):
            os.environ["AWS_DEFAULT_REGION"] = "eu-north-1"
        self.db = DynamoDBService()
        self.telegram_token = self._get_telegram_token()
        self.default_group_id = self._get_default_group_id()

    def _get_telegram_token(self) -> str:
        """Get Telegram token from Parameter Store"""
        ssm = boto3.client("ssm")
        try:
            response = ssm.get_parameter(Name=f"/ubbc-bot/{self.environment}/telegram-bot-token", WithDecryption=True)
            return response["Parameter"]["Value"]
        except Exception as e:
            print(f"Error getting Telegram token: {e}")
            return ""

    def _get_default_group_id(self) -> str:
        """Get default group ID from environment or config"""
        # Test environment: -1003399818858, Prod: -1001662432692
        if self.environment == "test":
            return "-1003399818858"
        else:
            return "-1001662432692"

    def get_registered_customers(self) -> set[int]:
        """Get all registered customer Telegram user IDs"""
        try:
            # Get all customers from database
            response = self.db.customers_table.scan()
            customer_ids = set()

            for item in response.get("Items", []):
                if "telegram_user_id" in item:
                    customer_ids.add(int(item["telegram_user_id"]))

            return customer_ids
        except Exception as e:
            print(f"Error getting registered customers: {e}")
            return set()

    def get_group_members(self) -> set[int]:
        """Get all members of the default group"""
        try:
            # Get all chat members using getChatMember for each registered customer
            # and try to get recent chat members
            member_ids = set()

            # First get administrators
            admin_url = f"https://api.telegram.org/bot{self.telegram_token}/getChatAdministrators"
            admin_response = requests.get(admin_url, params={"chat_id": self.default_group_id})

            if admin_response.ok:
                admins = admin_response.json().get("result", [])
                for admin in admins:
                    if "user" in admin and not admin["user"].get("is_bot", False):
                        member_ids.add(admin["user"]["id"])
                        print(
                            f"Admin: {admin['user'].get('first_name', 'Unknown')} "
                            f"(@{admin['user'].get('username', 'no_username')}) - ID: {admin['user']['id']}"
                        )

            # Try to get chat member info for each registered customer
            registered_customers = self.get_registered_customers()
            print(f"\nChecking membership for {len(registered_customers)} registered customers...")

            for customer_id in registered_customers:
                try:
                    member_url = f"https://api.telegram.org/bot{self.telegram_token}/getChatMember"
                    member_response = requests.get(
                        member_url, params={"chat_id": self.default_group_id, "user_id": customer_id}
                    )

                    if member_response.ok:
                        member_data = member_response.json().get("result", {})
                        status = member_data.get("status", "unknown")

                        # Member is in group if status is not 'left' or 'kicked'
                        if status in ["creator", "administrator", "member", "restricted"]:
                            member_ids.add(customer_id)
                            user_info = member_data.get("user", {})
                            # Get registered name from database
                            customer_details = self.get_customer_details(customer_id)
                            if customer_details:
                                reg_first = (
                                    customer_details["first_name"] if customer_details["first_name"] != "N/A" else ""
                                )
                                reg_last = (
                                    customer_details["last_name"] if customer_details["last_name"] != "N/A" else ""
                                )
                                registered_name = f"{reg_first} {reg_last}".strip() or "N/A"
                                print(
                                    f"Member: {user_info.get('first_name', 'Unknown')} "
                                    f"(@{user_info.get('username', 'no_username')}) - ID: {customer_id} - "
                                    f"Status: {status} - Registered: {registered_name}"
                                )
                            else:
                                print(
                                    f"Member: {user_info.get('first_name', 'Unknown')} "
                                    f"(@{user_info.get('username', 'no_username')}) - "
                                    f"ID: {customer_id} - Status: {status}"
                                )
                        else:
                            # Get registered name from database for non-members too
                            customer_details = self.get_customer_details(customer_id)
                            if customer_details:
                                reg_first = (
                                    customer_details["first_name"] if customer_details["first_name"] != "N/A" else ""
                                )
                                reg_last = (
                                    customer_details["last_name"] if customer_details["last_name"] != "N/A" else ""
                                )
                                registered_name = f"{reg_first} {reg_last}".strip() or "N/A"
                                print(
                                    f"Not in group: ID {customer_id} - Status: {status} - Registered: {registered_name}"
                                )
                            else:
                                print(f"Not in group: ID {customer_id} - Status: {status}")
                    else:
                        print(
                            f"Cannot check: ID {customer_id} - "
                            f"{member_response.json().get('description', 'Unknown error')}"
                        )

                except Exception as e:
                    print(f"Error checking member {customer_id}: {e}")

            print(f"\nFound {len(member_ids)} total group members")
            return member_ids

        except Exception as e:
            print(f"Error getting group members: {e}")
            return set()

    def get_customer_details(self, telegram_user_id: int) -> dict[str, Any]:
        """Get customer details by Telegram user ID"""
        try:
            customer = self.db.get_customer_by_telegram_id(telegram_user_id)
            if customer:
                return {
                    "customer_id": customer.customer_id,
                    "telegram_user_id": customer.telegram_user_id,
                    "username": customer.username or "N/A",
                    "first_name": customer.first_name or "N/A",
                    "last_name": customer.last_name or "N/A",
                    "authorization_status": customer.authorization_status,
                    "created_at": customer.created_at.isoformat()
                    if customer.created_at and hasattr(customer.created_at, "isoformat")
                    else str(customer.created_at)
                    if customer.created_at
                    else "N/A",
                }
            return {}
        except Exception as e:
            print(f"Error getting customer details for {telegram_user_id}: {e}")
            return {}

    def _get_user_credentials(self) -> dict[str, str]:
        """Get the admin user-account credentials from Parameter Store"""
        names = [
            f"/ubbc-bot/{self.environment}/telegram-api-id",
            f"/ubbc-bot/{self.environment}/telegram-api-hash",
            f"/ubbc-bot/{self.environment}/telegram-session",
        ]
        response = boto3.client("ssm").get_parameters(Names=names, WithDecryption=True)
        params = {p["Name"].split("/")[-1]: p["Value"] for p in response["Parameters"]}
        missing = [n for n in ("telegram-api-id", "telegram-api-hash", "telegram-session") if not params.get(n)]
        if missing:
            raise RuntimeError(f"Missing user-account parameters: {', '.join(missing)}")
        return {
            "api_id": params["telegram-api-id"],
            "api_hash": params["telegram-api-hash"],
            "session": params["telegram-session"],
        }

    @staticmethod
    def normalize_participants(participants) -> tuple[dict[int, dict[str, str]], dict[str, int]]:
        """Turn Telethon participants into {user_id: info}. Bots and deleted accounts are skipped."""
        members: dict[int, dict[str, str]] = {}
        skipped = {"bots": 0, "deleted": 0}
        for p in participants:
            if getattr(p, "bot", False):
                skipped["bots"] += 1
            elif getattr(p, "deleted", False):
                skipped["deleted"] += 1
            else:
                members[int(p.id)] = {
                    "first_name": getattr(p, "first_name", None) or "",
                    "last_name": getattr(p, "last_name", None) or "",
                    "username": getattr(p, "username", None) or "",
                }
        return members, skipped

    async def _fetch_participants(self):
        """List all participants of the default group with the admin user account (read-only)"""
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        creds = self._get_user_credentials()
        client = TelegramClient(StringSession(creds["session"]), int(creds["api_id"]), creds["api_hash"])
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError("User account session is not authorized")
            await client.get_dialogs()  # fill the entity cache so the group can be resolved
            group = await client.get_entity(int(self.default_group_id))
            return await client.get_participants(group)
        finally:
            await client.disconnect()

    def get_user_account_participants(self) -> tuple[dict[int, dict[str, str]], dict[str, int]]:
        """All group members as seen by the admin user account"""
        import asyncio

        return self.normalize_participants(asyncio.run(self._fetch_participants()))

    def get_unapproved_group_members(
        self, members: dict[int, dict[str, str]], registered_customers: set[int]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split group members the bot has not approved.

        Returns (registered customers whose status is not approved, unregistered members).
        """
        unapproved_customers = []
        for user_id in sorted(set(members) & registered_customers):
            details = self.get_customer_details(user_id)
            if details and details["authorization_status"] != AuthorizationStatus.APPROVED.value:
                unapproved_customers.append(details)

        unregistered = [{"id": user_id, **members[user_id]} for user_id in sorted(set(members) - registered_customers)]
        return unapproved_customers, unregistered

    def _print_unapproved_members(self, group_members: set[int], registered_customers: set[int]):
        """Print group members that the bot has not approved (section C)"""
        print("\n=== (C) GROUP MEMBERS NOT APPROVED IN THE BOT ===")

        skipped = {"bots": 0, "deleted": 0}
        try:
            members, skipped = self.get_user_account_participants()
            print(f"Source: admin user account ({len(members)} members, excluding bots and deleted accounts)")
            complete = True
        except Exception as e:
            print(f"Could not list members with the user account ({e}).")
            print("Falling back to the members the Bot API can see.")
            members = {user_id: {} for user_id in group_members}
            complete = False

        unapproved_customers, unregistered = self.get_unapproved_group_members(members, registered_customers)
        print(f"Count: {len(unapproved_customers) + len(unregistered)}")

        if unapproved_customers:
            print(f"\nRegistered, not approved ({len(unapproved_customers)}):")
            for details in unapproved_customers:
                name = f"{details['first_name']} {details['last_name']}".strip()
                print(
                    f"  • {name} (@{details['username']}) - ID: {details['telegram_user_id']} - "
                    f"Status: {details['authorization_status']}"
                )

        if unregistered:
            print(f"\nNot registered ({len(unregistered)}):")
            for member in unregistered:
                name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip() or "N/A"
                username = member.get("username") or "no_username"
                print(f"  • {name} (@{username}) - ID: {member['id']}")

        if complete:
            print(f"\nSkipped: {skipped['bots']} bots, {skipped['deleted']} deleted accounts.")
        else:
            print(
                "\nNote: without the user account, members who are neither administrators nor "
                "registered customers cannot be listed, so they are missing here."
            )

    def analyze(self, show_unapproved: bool = False):
        """Perform the analysis and print results"""
        print(f"=== Group Customer Analysis for {self.environment.upper()} environment ===\n")
        print(f"Default Group ID: {self.default_group_id}")

        # Get data
        registered_customers = self.get_registered_customers()
        group_members = self.get_group_members()

        print(f"\nRegistered customers: {len(registered_customers)}")
        print(f"Accessible group members: {len(group_members)}")

        # A) Customers not in group (based on accessible members)
        customers_not_in_group = registered_customers - group_members

        # B) Group members not registered as customers
        group_members_not_customers = group_members - registered_customers

        print("\n=== (A) CUSTOMERS NOT IN DEFAULT GROUP ===")
        print(f"Count: {len(customers_not_in_group)}")

        if customers_not_in_group:
            print("\nDetails:")
            for user_id in sorted(customers_not_in_group):
                details = self.get_customer_details(user_id)
                if details:
                    telegram_name = f"{details['first_name']} {details['last_name']}".strip()
                    registered_first = details["first_name"] if details["first_name"] != "N/A" else ""
                    registered_last = details["last_name"] if details["last_name"] != "N/A" else ""
                    registered_name = f"{registered_first} {registered_last}".strip() or "N/A"
                    print(
                        f"  • {telegram_name} (@{details['username']}) - ID: {user_id} - "
                        f"Status: {details['authorization_status']} - Registered: {registered_name}"
                    )
        else:
            print("All registered customers are in the accessible group member list.")

        print("\n=== (B) GROUP MEMBERS NOT REGISTERED AS CUSTOMERS ===")
        print(f"Count: {len(group_members_not_customers)}")

        if group_members_not_customers:
            print("\nDetails:")
            print("Note: These are group administrators not registered as customers.")
            print("Use Telegram API or bot commands to get more details about these users.")
            for user_id in sorted(group_members_not_customers):
                print(f"  • Telegram User ID: {user_id}")
        else:
            print("All accessible group members are registered customers.")

        if show_unapproved:
            self._print_unapproved_members(group_members, registered_customers)

        print("\n=== SUMMARY ===")
        print(f"• Registered customers: {len(registered_customers)}")
        print(f"• Accessible group members: {len(group_members)}")
        print(f"• Customers not in group: {len(customers_not_in_group)}")
        print(f"• Group members not customers: {len(group_members_not_customers)}")

        print("\n=== LIMITATIONS ===")
        print("• Telegram Bot API only allows access to administrators and users who have interacted with the bot")
        print("• Regular group members are not accessible via API for privacy reasons")
        print("• For complete analysis, manual group inspection or bot interaction logs would be needed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze customers vs group members")
    parser.add_argument(
        "--env", choices=["test", "prod"], default="test", help="Environment to analyze (default: test)"
    )

    parser.add_argument(
        "--show-unapproved",
        action="store_true",
        help="Also list group members the bot has not approved (default: off)",
    )

    args = parser.parse_args()

    # Set environment variables
    os.environ["ENVIRONMENT"] = args.env
    os.environ["DYNAMODB_TABLE_PREFIX"] = f"ubbc-bot-{args.env}"

    analyzer = GroupCustomerAnalyzer(args.env)
    analyzer.analyze(show_unapproved=args.show_unapproved)


if __name__ == "__main__":
    main()
