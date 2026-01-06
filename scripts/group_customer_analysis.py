#!/usr/bin/env python3
"""
Group Customer Analysis Script

This script compares registered customers with members of the default Telegram group to identify:
A) Customers not in the default group
B) Group members not registered as customers
"""

import os
import sys
import boto3
import requests
from typing import Set, List, Dict, Any

# Add src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.database import DynamoDBService
from models.entities import Customer

class GroupCustomerAnalyzer:
    def __init__(self, environment: str = 'test'):
        self.environment = environment
        # Set AWS region if not set
        if not os.environ.get('AWS_DEFAULT_REGION'):
            os.environ['AWS_DEFAULT_REGION'] = 'eu-north-1'
        self.db = DynamoDBService()
        self.telegram_token = self._get_telegram_token()
        self.default_group_id = self._get_default_group_id()
        
    def _get_telegram_token(self) -> str:
        """Get Telegram token from Parameter Store"""
        ssm = boto3.client('ssm')
        try:
            response = ssm.get_parameter(
                Name=f'/ubbc-bot/{self.environment}/telegram-bot-token',
                WithDecryption=True
            )
            return response['Parameter']['Value']
        except Exception as e:
            print(f"Error getting Telegram token: {e}")
            return ""
    
    def _get_default_group_id(self) -> str:
        """Get default group ID from environment or config"""
        # Test environment: -1003399818858, Prod: -1001662432692
        if self.environment == 'test':
            return '-1003399818858'
        else:
            return '-1001662432692'
    
    def get_registered_customers(self) -> Set[int]:
        """Get all registered customer Telegram user IDs"""
        try:
            # Get all customers from database
            response = self.db.customers_table.scan()
            customer_ids = set()
            
            for item in response.get('Items', []):
                if 'telegram_user_id' in item:
                    customer_ids.add(int(item['telegram_user_id']))
            
            return customer_ids
        except Exception as e:
            print(f"Error getting registered customers: {e}")
            return set()
    
    def get_group_members(self) -> Set[int]:
        """Get all members of the default group"""
        try:
            # Get all chat members using getChatMember for each registered customer
            # and try to get recent chat members
            member_ids = set()
            
            # First get administrators
            admin_url = f"https://api.telegram.org/bot{self.telegram_token}/getChatAdministrators"
            admin_response = requests.get(admin_url, params={'chat_id': self.default_group_id})
            
            if admin_response.ok:
                admins = admin_response.json().get('result', [])
                for admin in admins:
                    if 'user' in admin and not admin['user'].get('is_bot', False):
                        member_ids.add(admin['user']['id'])
                        print(f"Admin: {admin['user'].get('first_name', 'Unknown')} (@{admin['user'].get('username', 'no_username')}) - ID: {admin['user']['id']}")
            
            # Try to get chat member info for each registered customer
            registered_customers = self.get_registered_customers()
            print(f"\nChecking membership for {len(registered_customers)} registered customers...")
            
            for customer_id in registered_customers:
                try:
                    member_url = f"https://api.telegram.org/bot{self.telegram_token}/getChatMember"
                    member_response = requests.get(member_url, params={
                        'chat_id': self.default_group_id,
                        'user_id': customer_id
                    })
                    
                    if member_response.ok:
                        member_data = member_response.json().get('result', {})
                        status = member_data.get('status', 'unknown')
                        
                        # Member is in group if status is not 'left' or 'kicked'
                        if status in ['creator', 'administrator', 'member', 'restricted']:
                            member_ids.add(customer_id)
                            user_info = member_data.get('user', {})
                            # Get registered name from database
                            customer_details = self.get_customer_details(customer_id)
                            if customer_details:
                                reg_first = customer_details['first_name'] if customer_details['first_name'] != 'N/A' else ''
                                reg_last = customer_details['last_name'] if customer_details['last_name'] != 'N/A' else ''
                                registered_name = f"{reg_first} {reg_last}".strip() or 'N/A'
                                print(f"Member: {user_info.get('first_name', 'Unknown')} (@{user_info.get('username', 'no_username')}) - ID: {customer_id} - Status: {status} - Registered: {registered_name}")
                            else:
                                print(f"Member: {user_info.get('first_name', 'Unknown')} (@{user_info.get('username', 'no_username')}) - ID: {customer_id} - Status: {status}")
                        else:
                            # Get registered name from database for non-members too
                            customer_details = self.get_customer_details(customer_id)
                            if customer_details:
                                reg_first = customer_details['first_name'] if customer_details['first_name'] != 'N/A' else ''
                                reg_last = customer_details['last_name'] if customer_details['last_name'] != 'N/A' else ''
                                registered_name = f"{reg_first} {reg_last}".strip() or 'N/A'
                                print(f"Not in group: ID {customer_id} - Status: {status} - Registered: {registered_name}")
                            else:
                                print(f"Not in group: ID {customer_id} - Status: {status}")
                    else:
                        print(f"Cannot check: ID {customer_id} - {member_response.json().get('description', 'Unknown error')}")
                        
                except Exception as e:
                    print(f"Error checking member {customer_id}: {e}")
            
            print(f"\nFound {len(member_ids)} total group members")
            return member_ids
            
        except Exception as e:
            print(f"Error getting group members: {e}")
            return set()
    
    def get_customer_details(self, telegram_user_id: int) -> Dict[str, Any]:
        """Get customer details by Telegram user ID"""
        try:
            customer = self.db.get_customer_by_telegram_id(telegram_user_id)
            if customer:
                return {
                    'customer_id': customer.customer_id,
                    'telegram_user_id': customer.telegram_user_id,
                    'username': customer.username or 'N/A',
                    'first_name': customer.first_name or 'N/A',
                    'last_name': customer.last_name or 'N/A',
                    'authorization_status': customer.authorization_status,
                    'created_at': customer.created_at.isoformat() if customer.created_at and hasattr(customer.created_at, 'isoformat') else str(customer.created_at) if customer.created_at else 'N/A'
                }
            return {}
        except Exception as e:
            print(f"Error getting customer details for {telegram_user_id}: {e}")
            return {}
    
    def analyze(self):
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
        
        print(f"\n=== (A) CUSTOMERS NOT IN DEFAULT GROUP ===")
        print(f"Count: {len(customers_not_in_group)}")
        
        if customers_not_in_group:
            print("\nDetails:")
            for user_id in sorted(customers_not_in_group):
                details = self.get_customer_details(user_id)
                if details:
                    telegram_name = f"{details['first_name']} {details['last_name']}".strip()
                    registered_first = details['first_name'] if details['first_name'] != 'N/A' else ''
                    registered_last = details['last_name'] if details['last_name'] != 'N/A' else ''
                    registered_name = f"{registered_first} {registered_last}".strip() or 'N/A'
                    print(f"  • {telegram_name} (@{details['username']}) - ID: {user_id} - Status: {details['authorization_status']} - Registered: {registered_name}")
        else:
            print("All registered customers are in the accessible group member list.")
        
        print(f"\n=== (B) GROUP MEMBERS NOT REGISTERED AS CUSTOMERS ===")
        print(f"Count: {len(group_members_not_customers)}")
        
        if group_members_not_customers:
            print("\nDetails:")
            print("Note: These are group administrators not registered as customers.")
            print("Use Telegram API or bot commands to get more details about these users.")
            for user_id in sorted(group_members_not_customers):
                print(f"  • Telegram User ID: {user_id}")
        else:
            print("All accessible group members are registered customers.")
        
        print(f"\n=== SUMMARY ===")
        print(f"• Registered customers: {len(registered_customers)}")
        print(f"• Accessible group members: {len(group_members)}")
        print(f"• Customers not in group: {len(customers_not_in_group)}")
        print(f"• Group members not customers: {len(group_members_not_customers)}")
        
        print(f"\n=== LIMITATIONS ===")
        print("• Telegram Bot API only allows access to administrators and users who have interacted with the bot")
        print("• Regular group members are not accessible via API for privacy reasons")
        print("• For complete analysis, manual group inspection or bot interaction logs would be needed")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze customers vs group members')
    parser.add_argument('--env', choices=['test', 'prod'], default='test',
                       help='Environment to analyze (default: test)')
    
    args = parser.parse_args()
    
    # Set environment variables
    os.environ['ENVIRONMENT'] = args.env
    os.environ['DYNAMODB_TABLE_PREFIX'] = f'ubbc-bot-{args.env}'
    
    analyzer = GroupCustomerAnalyzer(args.env)
    analyzer.analyze()

if __name__ == '__main__':
    main()