from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, UTC
from repositories.base_repository import BaseRepository
from repositories.system_repository import SystemRepository
from models.entities import Offer
from services.offer_cache import OfferCache

class OfferRepository(BaseRepository):
    def __init__(self, system_repo: SystemRepository):
        super().__init__("offers")
        self.system_repo = system_repo

    def create_offer(self, offer: Offer) -> bool:
        try:
            # Get next offer ID if not set
            if offer.offer_id == 0:
                offer.offer_id = self.system_repo.get_next_id('offer_id')
            
            item = self._prepare_item(offer.__dict__)
            self.table.put_item(Item=item)
            
            # Invalidate cache
            OfferCache.invalidate_cache()
            
            return True
        except Exception as e:
            print(f"Error creating offer: {e}")
            return False

    def get_offer(self, offer_id: int) -> Optional[Offer]:
        try:
            # Ensure offer_id is an integer (handle float inputs)
            offer_id = int(offer_id)
            response = self.table.get_item(Key={'offer_id': offer_id})
            if 'Item' in response:
                item = response['Item']
                # Convert Decimal fields to appropriate types
                if 'wholesale_box_size' in item:
                    item['wholesale_box_size'] = int(item['wholesale_box_size'])
                # Remove deprecated fields for backward compatibility
                item.pop('min_quantity_breakeven', None)
                return Offer(**item)
            return None
        except Exception as e:
            print(f"Error getting offer: {e}")
            return None

    def list_offers(self) -> List[Offer]:
        """Get all offers with caching"""
        # Pass self as 'db' because OfferCache expects an object with _list_offers_uncached
        return OfferCache.get_offers(self)
    
    def _list_offers_uncached(self) -> List[Offer]:
        """Internal method to get offers without caching (called by OfferCache)"""
        try:
            response = self.table.scan(ConsistentRead=True)
            offers = []
            for item in response.get('Items', []):
                # Convert Decimal fields to appropriate types
                if 'wholesale_box_size' in item:
                    item['wholesale_box_size'] = int(item['wholesale_box_size'])
                # Remove deprecated fields for backward compatibility
                item.pop('min_quantity_breakeven', None)
                offers.append(Offer(**item))
            return offers
        except Exception as e:
            print(f"Error listing offers: {e}")
            return []
    
    def list_sold_out_offers_recent(self, days: int = 7) -> List[Offer]:
        """Get sold out offers from last N days"""
        try:
            cutoff_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()
            
            response = self.table.scan(
                FilterExpression='#status = :status AND created_at >= :cutoff',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'sold_out',
                    ':cutoff': cutoff_date
                }
            )
            return [Offer(**item) for item in response.get('Items', [])]
        except Exception as e:
            print(f"Error listing recent sold out offers: {e}")
            return []

    def update_offer(self, offer_id: int, updates: Dict[str, Any]) -> bool:
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
                Key={'offer_id': offer_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values
            )
            
            # Invalidate cache AFTER successful update
            OfferCache.invalidate_cache()
            
            return True
        except Exception as e:
            print(f"Error updating offer: {e}")
            return False
    
    def append_offer_image(self, offer_id: int, image_url: str) -> bool:
        """Atomically append an image to offer's images list"""
        try:
            self.table.update_item(
                Key={'offer_id': offer_id},
                UpdateExpression='SET images = list_append(if_not_exists(images, :empty_list), :new_image)',
                ExpressionAttributeValues={
                    ':new_image': [image_url],
                    ':empty_list': []
                }
            )
            
            # Invalidate cache
            OfferCache.invalidate_cache()
            
            return True
        except Exception as e:
            print(f"Error appending image to offer: {e}")
            return False
