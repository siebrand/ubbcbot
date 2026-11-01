#!/usr/bin/env python3
"""
Update legacy customers with default values for location and is_guest fields.

Usage:
    python scripts/update_legacy_customers.py <environment>

Arguments:
    environment: test or prod
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def update_legacy_customers(environment):
    """Update customers missing location or is_guest fields"""
    import boto3

    # Connect directly to the correct table
    dynamodb = boto3.resource("dynamodb")
    table_name = f"ubbc-bot-{environment}-customers"
    customers_table = dynamodb.Table(table_name)

    print(f"Connected to table: {table_name}\n")

    # Scan raw DynamoDB table to check for missing fields
    response = customers_table.scan()
    items = response.get("Items", [])

    updated_count = 0
    skipped_count = 0

    for item in items:
        updates = {}

        # Debug: show what fields exist
        has_location = "location" in item
        has_is_guest = "is_guest" in item
        print(f"Customer {item['customer_id'][:8]}: has_location={has_location}, has_is_guest={has_is_guest}")

        # Check if location field exists in DynamoDB (not just empty)
        if "location" not in item:
            updates["location"] = "Venster, Berlijnplein 520, Utrecht"

        # Check if is_guest field exists in DynamoDB
        if "is_guest" not in item:
            updates["is_guest"] = False

        if updates:
            customer_id = item["customer_id"]
            # Update using boto3 directly
            update_expr = "SET " + ", ".join([f"#{k} = :{k}" for k in updates])
            expr_attr_names = {f"#{k}": k for k in updates}
            expr_attr_values = {f":{k}": v for k, v in updates.items()}

            try:
                customers_table.update_item(
                    Key={"customer_id": customer_id},
                    UpdateExpression=update_expr,
                    ExpressionAttributeNames=expr_attr_names,
                    ExpressionAttributeValues=expr_attr_values,
                )
                updated_count += 1
                print(f"✅ Updated customer {customer_id}: {updates}")
            except Exception as e:
                print(f"❌ Failed to update customer {customer_id}: {e}")
        else:
            skipped_count += 1

    print("\n📊 Summary:")
    print(f"   Updated: {updated_count} customers")
    print(f"   Skipped: {skipped_count} customers (already have values)")
    print(f"   Total: {len(items)} customers")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ["test", "prod"]:
        print("Usage: python scripts/update_legacy_customers.py <environment>")
        print("Environment: test or prod")
        sys.exit(1)

    environment = sys.argv[1]
    print(f"🔄 Updating legacy customers in {environment.upper()} environment...\n")
    update_legacy_customers(environment)
    print("\n✅ Done!")
