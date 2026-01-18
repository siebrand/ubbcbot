from typing import Optional, List, Dict, Any
from repositories.base_repository import BaseRepository
from models.entities import Supplier

class SupplierRepository(BaseRepository):
    def __init__(self):
        super().__init__("suppliers")

    def create_supplier(self, supplier: Supplier) -> bool:
        try:
            # Check for duplicate name (case-insensitive)
            existing = self.get_supplier_by_name(supplier.name)
            if existing:
                return False
            
            item = self._prepare_item(supplier.__dict__)
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            print(f"Error creating supplier: {e}")
            return False

    def get_supplier(self, supplier_id: str) -> Optional[Supplier]:
        try:
            response = self.table.get_item(Key={'supplier_id': supplier_id})
            if 'Item' in response:
                return Supplier(**response['Item'])
            return None
        except Exception as e:
            print(f"Error getting supplier: {e}")
            return None

    def get_supplier_by_name(self, name: str) -> Optional[Supplier]:
        try:
            response = self.table.scan(
                FilterExpression='#name = :name',
                ExpressionAttributeNames={'#name': 'name'},
                ExpressionAttributeValues={':name': name.strip()}
            )
            items = response.get('Items', [])
            if items:
                return Supplier(**items[0])
            return None
        except Exception as e:
            print(f"Error getting supplier by name: {e}")
            return None

    def update_supplier(self, supplier_id: str, updates: Dict[str, Any]) -> bool:
        try:
            update_expression = "SET "
            expression_values = {}
            expression_names = {}
            
            for key, value in updates.items():
                update_expression += f"#{key} = :{key}, "
                expression_values[f":{key}"] = value
                expression_names[f"#{key}"] = key
            
            update_expression = update_expression.rstrip(", ")
            
            self.table.update_item(
                Key={'supplier_id': supplier_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            return True
        except Exception as e:
            print(f"Error updating supplier: {e}")
            return False

    def list_suppliers(self) -> List[Supplier]:
        try:
            response = self.table.scan()
            return [Supplier(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error listing suppliers: {e}")
            return []
