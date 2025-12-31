from typing import Dict, Any
from handlers.base_handler import BaseHandler

class ChangelogCommands(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.changelog_entries = [
            {
                "title": "Up to 2025-12-31",
                "content": """<b>User-Facing Updates</b>
• <b>Enhanced Order Display</b> - Added offer ID to each line in /my_orders for better identification
• <b>Improved Order Management</b> - Added /delete_cancelled command to remove cancelled orders from personal register
• <b>Better Operation Control</b> - New /cancel command to clear pending operations and text input prompts
• <b>Cleaner Group Experience</b> - Removed order buttons from default channel offer announcements

<b>Admin-Facing Updates</b>
• <b>Enhanced Order Cancellation</b> - Improved /cancel_order with better detection logic and detailed confirmation dialogs
• <b>Advanced Order Tracking</b> - Updated /user_orders to match /my_orders format with short order IDs for easier reference
• <b>Partial Order ID Support</b> - /cancel_order now matches on first 8 characters of order ID for faster cancellation
• <b>Comprehensive Order Management</b> - Added cancellation reasons to all order cancellation workflows
• <b>System Maintenance</b> - New /delete_old_cancelled command to remove cancelled orders older than 7 days
• <b>Data Integrity</b> - Added /audit_orders command to fix orders missing update_date timestamps
• <b>Enhanced Offer Management</b> - New /offer_orders command with paginated button workflow to view all orders for specific offers
• <b>Improved Box Management</b> - Better wholesale ordering precision and box status filtering with custom quantity options
• <b>Advanced Auditing</b> - New /audit_offer command to check and fix order/box capacity discrepancies
• <b>Better Error Handling</b> - Improved race condition prevention and capacity management
• <b>Streamlined Workflows</b> - Enhanced button-based interfaces for /cancel_order, /user_orders, and /order_for commands
• <b>Interactive Order Placement</b> - New button-based workflow for /order_for: username → offer selection → quantity (1/2/Other)
• <b>Flexible Quantity Input</b> - Added "Other" quantity option with text input for /order_for command
• <b>Enhanced User Management</b> - Improved user disambiguation and filtering for approve_user command
• <b>Comprehensive Admin Panel</b> - Enhanced interactive workflows with supplier full name support
• <b>System Reliability</b> - Automatic order update_date setting, better database consistency, and duplicate string removal"""
            },
            {
                "title": "Up to 2025-12-29",
                "content": """<b>User-Facing Updates</b>
• <b>Enhanced Order Management</b> - Improved order display with better formatting and status indicators
• <b>Better Error Messages</b> - More descriptive messages when offers are sold out or unavailable
• <b>Improved Order Notifications</b> - Clearer status updates and better formatting in order confirmations

<b>Admin-Facing Updates</b>
• <b>Button-Based Admin Workflows</b> - Interactive UI for /user_orders, /cancel_order, and /order_for commands
• <b>Enhanced Customer Search</b> - Unified search with disambiguation for partial name matches across all commands
• <b>Comprehensive Admin Panel</b> - New /admin command with organized button interface for all admin functions
• <b>Improved Order Cancellation</b> - Step-by-step workflow with user selection and order listing with cancel option
• <b>Enhanced User Management</b> - Better customer search and editing with consolidated methods
• <b>Streamlined Order Placement</b> - /order_for now uses button workflow: username → offer selection → quantity (1/2/Other)
• <b>Better Delivery Management</b> - Enhanced wholesale delivery and labeling completion workflows
• <b>Improved Box Status Tracking</b> - Better status transitions and capacity management
• <b>Enhanced CSV Exports</b> - Improved order exports with better formatting and status filtering
• <b>Comprehensive Help System</b> - Organized help sections with detailed command documentation"""
            },
            {
                "title": "Up to 2025-12-26",
                "content": """<b>User-Facing Updates</b>
• <b>Enhanced Privacy Protection</b> - Group order announcements now show abbreviated names ("Firstname L.") instead of full names for privacy
• <b>Improved Offer Browsing</b> - New <code>/list_offers sold_out</code> parameter to view recently sold out offers from the last 7 days
• <b>Better availability indicators</b> - Order announcements show "sufficient available" vs specific counts
• <b>Bold formatting</b> - Offer IDs and names in listings for better readability
• <b>Cleaner offer displays</b> - Removed square brackets around IDs
• <b>Multiple Image Support</b> - Offers with multiple images now display as media groups instead of single photos
• <b>Complete Internationalization</b> - Full Dutch and English language support throughout the bot with proper translation system

<b>Admin-Facing Updates</b>
• <b>Enhanced Order Management</b> - PM notification status feedback when private messages to users fail with clear explanations
• <b>Improved order placement workflow</b> - Better error handling and user feedback for order limits
• <b>Advanced User Management</b> - Improved user pagination with 20 users per page and enhanced navigation
• <b>Better user search and filtering</b> - Enhanced user approval process with streamlined edit workflow
• <b>Offer Management Improvements</b> - Consolidated offer editing interface with full functionality in <code>/offer_details</code>
• <b>Edit Offer button</b> - Direct access from offer details view for quick editing
• <b>Seamless editing workflow</b> - Return to edit menu after field updates with maintained context
• <b>System Reliability</b> - Improved HTTP request handling with proper timeouts and better error handling
• <b>Modular service architecture</b> - Better maintainability with reduced code duplication and improved callback handling"""
            },
            {
                "title": "Up to 2025-12-25",
                "content": """<b>User-Facing Updates</b>
• <b>New /offer_details command</b> - View detailed offer information with images and descriptions
• <b>Interactive order buttons</b> - Click buttons to place orders instead of typing commands
• <b>Rich offer displays</b> - Offers now show images, detailed descriptions, and better formatting
• <b>Cleaner interface</b> - Simplified offer titles and improved readability
• <b>Better help system</b> - Enhanced help with clickable links and better organization

<b>Admin-Facing Updates</b>
• <b>Staged offer publishing</b> - Create draft offers, add details/images, then publish when ready
• <b>Interactive offer creation</b> - Button-based workflow for creating and editing offers
• <b>Multiple image uploads</b> - Add multiple images to offers with S3 storage
• <b>Enhanced offer preview</b> - Preview how offers appear to users before publishing
• <b>Continue editing buttons</b> - Seamless workflow after uploading images or updating descriptions
• <b>User search functionality</b> - Search users by name in /list_users command
• <b>Draft offer management</b> - Select and preview draft offers before publishing
• <b>Improved offer editing</b> - Interactive buttons for editing offer details"""
            }
        ]
    
    def handle_changelog(self, chat_id: int, user_id: int, page: int = 1) -> Dict[str, Any]:
        """Handle /changelog command with pagination"""
        if not self.changelog_entries:
            self._send_message(chat_id, "No changelog entries available.")
            return {'status': 'no_entries'}
        
        # Paginate entries (1 entry per page for readability)
        page_entries, total_pages = self._paginate_list(self.changelog_entries, page, 1)
        
        if not page_entries:
            self._send_message(chat_id, "Invalid page number.")
            return {'status': 'invalid_page'}
        
        entry = page_entries[0]
        message = f"📋 <b>UBBC Bot Changelog</b>\n\n<b>{entry['title']}</b>\n\n{entry['content']}"
        
        # Add pagination keyboard if needed
        keyboard = None
        if total_pages > 1:
            keyboard = self._build_pagination_keyboard(page, total_pages, "changelog")
        
        self._send_message(chat_id, message, parse_mode="HTML", reply_markup=keyboard)
        return {'status': 'success'}