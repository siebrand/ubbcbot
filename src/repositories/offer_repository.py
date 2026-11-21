import logging
from typing import Any

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from models.entities import Box, Offer, Order
from repositories.base_repository import BaseRepository
from repositories.system_repository import SystemRepository
from services.offer_cache import OfferCache

logger = logging.getLogger(__name__)


class OfferRepository(BaseRepository):
    def __init__(self, system_repo: SystemRepository):
        super().__init__("offers")
        self.system_repo = system_repo

    def create_offer(self, offer: Offer) -> bool:
        try:
            # Get next offer ID if not set
            if offer.offer_id == 0:
                offer.offer_id = self.system_repo.get_next_id("offer_id")

            item = self._prepare_item(offer.__dict__)
            self.table.put_item(Item=item)

            # Invalidate cache
            OfferCache.invalidate_cache()

            return True
        except Exception as e:
            logger.error(f"Error creating offer: {e}")
            return False

    def create_with_box_and_order(self, offer: Offer, box: Box, order: Order) -> bool:
        """Write a new offer, its box and its first order in one transaction: all three or none.

        The offer gets the next offer ID (a gap after a failed write is harmless); the box and the order point at
        it, and the order at the box. The box is written with its quantity already set. Each item only when its key
        does not exist yet. Returns False when the transaction was rejected or failed.
        """
        try:
            offer.offer_id = self.system_repo.get_next_id("offer_id")
            box.offer_id = order.offer_id = offer.offer_id
            order.box_id = box.box_id

            serializer = TypeSerializer()

            def put(table: str, entity, key: str) -> dict[str, Any]:
                item = {k: serializer.serialize(v) for k, v in self._prepare_item(entity.__dict__).items()}
                return {
                    "Put": {
                        "TableName": f"{self.table_prefix}-{table}",
                        "Item": item,
                        "ConditionExpression": f"attribute_not_exists({key})",
                    }
                }

            # A plain low-level client, as in OrderRepository.create_with_box_increment
            boto3.client("dynamodb").transact_write_items(
                TransactItems=[
                    put("offers", offer, "offer_id"),
                    put("boxes", box, "box_id"),
                    put("orders", order, "order_id"),
                ]
            )
        except ClientError as e:
            logger.error(
                f"Creating offer {offer.offer_id} with its box and order failed: {e.response['Error']['Code']}"
            )
            return False
        except Exception as e:
            logger.error(f"Creating offer {offer.offer_id} with its box and order failed: {type(e).__name__}")
            return False
        OfferCache.invalidate_cache()
        return True

    def get_offer(self, offer_id: int) -> Offer | None:
        try:
            # Ensure offer_id is an integer (handle float inputs)
            offer_id = int(offer_id)
            response = self.table.get_item(Key={"offer_id": offer_id})
            if "Item" in response:
                item = response["Item"]
                # Convert Decimal fields to appropriate types
                if "wholesale_box_size" in item:
                    item["wholesale_box_size"] = int(item["wholesale_box_size"])
                # Remove deprecated fields for backward compatibility
                item.pop("min_quantity_breakeven", None)
                return Offer(**item)
            return None
        except Exception as e:
            logger.error(f"Error getting offer: {e}")
            return None

    def list_offers(self) -> list[Offer]:
        """Get all offers with caching"""
        # Pass self as 'db' because OfferCache expects an object with _list_offers_uncached
        return OfferCache.get_offers(self)

    def _list_offers_uncached(self) -> list[Offer]:
        """Internal method to get offers without caching (called by OfferCache)"""
        try:
            offers = []
            for item in self._scan_items(ConsistentRead=True):
                # Convert Decimal fields to appropriate types
                if "wholesale_box_size" in item:
                    item["wholesale_box_size"] = int(item["wholesale_box_size"])
                # Remove deprecated fields for backward compatibility
                item.pop("min_quantity_breakeven", None)
                offers.append(Offer(**item))
            return offers
        except Exception as e:
            logger.error(f"Error listing offers: {e}")
            return []

    def update_offer(self, offer_id: int, updates: dict[str, Any]) -> bool:
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
                Key={"offer_id": offer_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_names,
                ExpressionAttributeValues=expression_values,
            )

            # Invalidate cache AFTER successful update
            OfferCache.invalidate_cache()

            return True
        except Exception as e:
            logger.error(f"Error updating offer: {e}")
            return False

    def append_offer_image(self, offer_id: int, image_url: str) -> bool:
        """Atomically append an image to offer's images list"""
        try:
            self.table.update_item(
                Key={"offer_id": offer_id},
                UpdateExpression="SET images = list_append(if_not_exists(images, :empty_list), :new_image)",
                ExpressionAttributeValues={":new_image": [image_url], ":empty_list": []},
            )

            # Invalidate cache
            OfferCache.invalidate_cache()

            return True
        except Exception as e:
            logger.error(f"Error appending image to offer: {e}")
            return False

    def delete_offer(self, offer_id: int) -> bool:
        try:
            self.table.delete_item(Key={"offer_id": offer_id})
            OfferCache.invalidate_cache()
            return True
        except Exception as e:
            logger.error(f"Error deleting offer: {e}")
            return False
