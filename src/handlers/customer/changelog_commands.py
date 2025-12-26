from typing import Dict, Any
from handlers.base_handler import BaseHandler

class ChangelogCommands(BaseHandler):
    def handle_changelog(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /changelog command"""
        changelog = """📋 <b>UBBC Bot Changelog</b>

<b>Up to 2025-12-26</b>

<b>User-Facing Updates</b>
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
• <b>Modular service architecture</b> - Better maintainability with reduced code duplication and improved callback handling

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Up to 2025-12-25</b>

<b>User-Facing Updates</b>
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

        self._send_message(chat_id, changelog, parse_mode="HTML")
        return {'status': 'success'}