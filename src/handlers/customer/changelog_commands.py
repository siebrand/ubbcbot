from typing import Dict, Any
from handlers.base_handler import BaseHandler

class ChangelogCommands(BaseHandler):
    def handle_changelog(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """Handle /changelog command"""
        changelog = """📋 *UBBC Bot Changelog*

*Latest Updates \\(December 2024\\)*

*User\\-Facing Updates*
• *Enhanced Privacy Protection* \\- Group order announcements now show abbreviated names \\(\\"Firstname L\\.\\"\\) instead of full names for privacy
• *Improved Offer Browsing* \\- New `/list_offers sold_out` parameter to view recently sold out offers from the last 7 days
• *Better availability indicators* \\- Order announcements show \\"sufficient available\\" vs specific counts
• *Bold formatting* \\- Offer IDs and names in listings for better readability
• *Cleaner offer displays* \\- Removed square brackets around IDs
• *Multiple Image Support* \\- Offers with multiple images now display as media groups instead of single photos
• *Complete Internationalization* \\- Full Dutch and English language support throughout the bot with proper translation system

*Admin\\-Facing Updates*
• *Enhanced Order Management* \\- PM notification status feedback when private messages to users fail with clear explanations
• *Improved order placement workflow* \\- Better error handling and user feedback for order limits
• *Advanced User Management* \\- Improved user pagination with 20 users per page and enhanced navigation
• *Better user search and filtering* \\- Enhanced user approval process with streamlined edit workflow
• *Offer Management Improvements* \\- Consolidated offer editing interface with full functionality in `/offer_details`
• *Edit Offer button* \\- Direct access from offer details view for quick editing
• *Seamless editing workflow* \\- Return to edit menu after field updates with maintained context
• *System Reliability* \\- Improved HTTP request handling with proper timeouts and better error handling
• *Modular service architecture* \\- Better maintainability with reduced code duplication and improved callback handling

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*Previous Updates \\(November 2024\\)*

*User\\-Facing Updates*
• *New /offer_details command* \\- View detailed offer information with images and descriptions
• *Interactive order buttons* \\- Click buttons to place orders instead of typing commands
• *Rich offer displays* \\- Offers now show images, detailed descriptions, and better formatting
• *Cleaner interface* \\- Simplified offer titles and improved readability
• *Better help system* \\- Enhanced help with clickable links and better organization

*Admin\\-Facing Updates*
• *Staged offer publishing* \\- Create draft offers, add details/images, then publish when ready
• *Interactive offer creation* \\- Button\\-based workflow for creating and editing offers
• *Multiple image uploads* \\- Add multiple images to offers with S3 storage
• *Enhanced offer preview* \\- Preview how offers appear to users before publishing
• *Continue editing buttons* \\- Seamless workflow after uploading images or updating descriptions
• *User search functionality* \\- Search users by name in /list_users command
• *Draft offer management* \\- Select and preview draft offers before publishing
• *Improved offer editing* \\- Interactive buttons for editing offer details"""

        self._send_message(chat_id, changelog, parse_mode="MarkdownV2")
        return {'status': 'success'}