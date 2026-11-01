from datetime import UTC, datetime, timedelta
from typing import Any

from models.entities import AuthorizationStatus

from .base_order_handler import BaseOrderHandler


class OrderMaintenance(BaseOrderHandler):
    """Handles order maintenance and cleanup functionality"""

    def handle_delete_old_orders(self, chat_id: int) -> dict[str, Any]:
        """Handle admin /delete_old_orders command - delete cancelled and completed orders older than 7 days"""
        try:
            # Calculate cutoff date (7 days ago)
            cutoff_date = datetime.now(UTC) - timedelta(days=7)

            # Get all customers
            customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)

            old_cancelled_orders = []
            old_completed_orders = []

            for customer in customers:
                # Get cancelled orders
                cancelled_orders = self.db.get_orders_by_customer_and_status(customer.customer_id, "cancelled")
                for order in cancelled_orders:
                    if order.update_date:
                        try:
                            update_date = datetime.fromisoformat(order.update_date.replace("Z", "+00:00"))
                            if update_date <= cutoff_date:
                                old_cancelled_orders.append(order)
                        except ValueError, AttributeError:
                            # Skip orders with invalid cancellation dates
                            continue

                # Get completed orders
                completed_orders = self.db.get_orders_by_customer_and_status(customer.customer_id, "completed")
                for order in completed_orders:
                    if order.update_date:
                        try:
                            update_date = datetime.fromisoformat(order.update_date.replace("Z", "+00:00"))
                            if update_date <= cutoff_date:
                                old_completed_orders.append(order)
                        except ValueError, AttributeError:
                            # Skip orders with invalid completion dates
                            continue

            if not old_cancelled_orders and not old_completed_orders:
                keyboard = {"inline_keyboard": [[{"text": self._t("back_to_admin"), "callback_data": "admin:main"}]]}
                self._send_message(chat_id, self._t("no_old_orders", chat_id), reply_markup=keyboard)
                return {"status": "no_old_orders"}

            # Delete old orders
            deleted_cancelled_count = 0
            deleted_completed_count = 0

            for order in old_cancelled_orders:
                if self.db.delete_order(order.order_id):
                    deleted_cancelled_count += 1

            for order in old_completed_orders:
                if self.db.delete_order(order.order_id):
                    deleted_completed_count += 1

            if deleted_cancelled_count > 0 or deleted_completed_count > 0:
                message = self._t(
                    "old_orders_deleted",
                    chat_id,
                    cancelled_count=deleted_cancelled_count,
                    completed_count=deleted_completed_count,
                )
                keyboard = {"inline_keyboard": [[{"text": self._t("back_to_admin"), "callback_data": "admin:main"}]]}
                self._send_message(chat_id, message, reply_markup=keyboard)
                return {
                    "status": "success",
                    "deleted_cancelled_count": deleted_cancelled_count,
                    "deleted_completed_count": deleted_completed_count,
                }
            else:
                keyboard = {"inline_keyboard": [[{"text": self._t("back_to_admin"), "callback_data": "admin:main"}]]}
                self._send_message(chat_id, self._t("failed_delete_old_orders", chat_id), reply_markup=keyboard)
                return {"status": "error"}

        except Exception as e:
            import logging

            logger = logging.getLogger()
            logger.error(f"Error in admin handle_delete_old_orders: {e}")
            self._send_message(chat_id, self._t("failed_delete_old_orders", chat_id))
            return {"status": "error"}

    def handle_audit_orders(self, chat_id: int) -> dict[str, Any]:
        """Handle /audit_orders command - add update_date to orders without it"""
        try:
            # Get all customers
            customers = self.db.get_customers_by_status(AuthorizationStatus.APPROVED.value)

            orders_without_update_date = []
            for customer in customers:
                orders = self.db.get_orders_by_customer(customer.customer_id)
                for order in orders:
                    if not order.update_date:
                        orders_without_update_date.append(order)

            if not orders_without_update_date:
                keyboard = {"inline_keyboard": [[{"text": self._t("back_to_admin"), "callback_data": "admin:main"}]]}
                self._send_message(chat_id, self._t("no_orders_missing_update_date", chat_id), reply_markup=keyboard)
                return {"status": "no_orders_to_audit"}

            # Update orders - update_date will be set automatically by update_order
            updated_count = 0

            for order in orders_without_update_date:
                if self.db.update_order(order.order_id, {}):
                    updated_count += 1

            if updated_count > 0:
                keyboard = {"inline_keyboard": [[{"text": self._t("back_to_admin"), "callback_data": "admin:main"}]]}
                self._send_message(
                    chat_id, self._t("orders_audit_completed", chat_id, count=updated_count), reply_markup=keyboard
                )
                return {"status": "success", "updated_count": updated_count}
            else:
                keyboard = {"inline_keyboard": [[{"text": self._t("back_to_admin"), "callback_data": "admin:main"}]]}
                self._send_message(chat_id, self._t("failed_audit_orders", chat_id), reply_markup=keyboard)
                return {"status": "error"}

        except Exception as e:
            import logging

            logger = logging.getLogger()
            logger.error(f"Error in handle_audit_orders: {e}")
            self._send_message(chat_id, self._t("failed_audit_orders", chat_id))
            return {"status": "error"}
