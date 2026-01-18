from typing import Dict, Any
from handlers.base_handler import BaseHandler

class ChangelogCommands(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.changelog_entries = [
            {
                "title": "Up to 2026-01-18",
                "content": """<b>User-Facing Updates</b>
• <b>Credit System</b> - New <code>/my_credit</code> command for customers to view their account balance
• <b>Command Standardization</b> - Renamed /offer_details to <code>/view_offer</code> for consistency
• <b>Improved Deep Links</b> - Offer links now use the standardized <code>view_offer</code> format

<b>Admin-Facing Updates</b>
• <b>Credit Management</b> - Complete system for issuing credits/charges (<code>/credit</code>) with automatic application to deliveries
• <b>Process Command Standardization</b> - Renamed workflow commands: <code>/process_payment</code> (was mark_paid), <code>/process_delivery</code> (was wholesale_delivery), and <code>/process_labeling</code> (was labeling_completed)
• <b>Callback Router Infrastructure</b> - Replaced monolithic callback handling with modular <code>CallbackRouter</code> (Phases 0-3 complete)
• <b>Database Architecture</b> - Completed migration to Repository pattern (Phases 4-8), slimming down core DatabaseService
• <b>Codebase Refactoring</b> - Completed massive refactoring of 23 command handlers and internal routing logic
• <b>Enhanced Wholesale</b> - Added pagination and alphabetical sorting to <code>/process_wholesale</code>
• <b>Legacy Cleanup</b> - Removed deprecated methods and updated test suites (179+ routing tests passing)"""
            },
            {
                "title": "Up to 2025-01-13",
                "content": """<b>User-Facing Updates</b>
• <b>Enhanced Order Display</b> - Localized dates with month abbreviations (e.g., "11 jan 26"), clickable offer links in order lists
• <b>Smart Subtotals</b> - Category subtotals with grand total (excludes cancelled/completed orders)
• <b>Visual Improvements</b> - Alternating diamond icons (🔸🔹) improve readability in long order lists
• <b>Better Offer Access</b> - Non-admins can view sold-out/completed offers if they have orders
• <b>Improved Notifications</b> - Restored availability display in group order announcements
• <b>Delivery & Payment Redesign</b> - Fancy HTML-formatted messages with pickup location
• <b>Bug Fixes</b> - Availability calculation restored, pagination fixed

<b>Admin-Facing Updates</b>
• <b>Command Naming Standardization</b> - 23 commands renamed to consistent action-object pattern (create_, list_, view_, update_, process_), permanent aliases for /order, /my_orders, /order_for
• <b>Order History & Audit Trail</b> - Complete audit system with automatic logging, financial tracking for payments/refunds, 5-year retention, database-level enforcement
• <b>Delivered Box Availability</b> - Smart box prioritization places orders in delivered boxes first, prevents unnecessary box creation, orders automatically marked ready_for_labeling
• <b>Streamlined Admin Panel</b> - Reduced from 9 to 7 categories with logical grouping, process next offer button for continuous workflows
• <b>Enhanced Workflows</b> - Return to admin menu after completing all deliveries/labeling/payments, complete help system with discounts/import/system sections
• <b>Centralized Configuration</b> - Admin user ID from environment variable (no hardcoding)
• <b>Order Display Consolidation</b> - Unified my_orders and user_orders logic reduces duplication
• <b>Data Correction Tools</b> - Script to fix import order status bugs, removed CONFIRMED status (simplified to pending → ordered → ready_for_labeling)
• <b>Improved Automatic Testing</b> - 212 passing tests (151 routing + 61 integration) with TDD approach for newly implemented features"""
            },
            {
                "title": "Up to 2025-01-12",
                "content": """<b>User-Facing Updates</b>
• <b>Enhanced Pagination</b> - Added pagination to /my_orders (20 lines per page) and /list_offers (20 offers per page) to prevent message length errors
• <b>Improved Offer Display</b> - Active offers now sorted newest-first for customers, making latest offers easier to find
• <b>Cleaner Offer Lists</b> - Removed availability reporting for completed and inactive offers, showing only relevant data
• <b>Performance Optimization</b> - Implemented caching for multiple entities, improving response times and reducing queries over 90%.

<b>Admin-Facing Updates</b>
• <b>Guest User System</b> - Added /add_guest and /list_guests commands for managing non-Telegram customers
• <b>Comprehensive Pagination System</b> - Enhanced pagination with first/last/jump buttons for /my_orders, /list_offers, /user_orders, /mark_paid, and /box_status
• <b>Order Import Feature</b> - New /import_orders command for CSV-based legacy order migration with validation and error reporting
• <b>Enhanced Box Status</b> - Added offer_id filter, logical sorting (by offer/status/box), and help option to /box_status
• <b>Offer Management</b> - Streamlined editing UX with auto-return to edit mode, prevented duplicate images on concurrent uploads
• <b>Performance Optimization</b> - Implemented offer caching with 5-minute TTL and batch loading, reducing queries by over 90%
• <b>Centralized Services</b> - Created BoxStatusManager and BoxDeletionService for consistent box operations across codebase
• <b>Improved Order Exports</b> - Added full export option with all fields, normalized CSV format for Google Sheets
• <b>Better Payment Tracking</b> - Enhanced /mark_paid with pagination, alphabetical sorting, and auto-return to list after confirmation
• <b>Delivery Overview Improvements</b> - Guest users processed last with different message format, no failed Telegram attempts
• <b>Box Status Refinements</b> - Boxes marked ORDERED based on fulfilled orders, not box count, preventing incorrect status
• <b>HTML Validation</b> - Added HTMLParser validation for offer names and descriptions to prevent Telegram parse errors
• <b>Code Quality</b> - Refactored order commands into focused modules, eliminated duplicate logic, improved test coverage
• <b>Internationalization</b> - Fixes i18n for admin UI placeholders, headers, and labels
• <b>System Reliability</b> - Fixed pagination callback parsing, mark_paid tests, box deletion logic, and offer sold-out detection
• <b>Workflow Simplification</b> - Removed MINIMUM_REACHED status and breakeven fields, simplified to open→full→ordered→delivered
• <b>Filter Enhancements</b> - Added status filtering to /list_offers (all, draft, active, soldout, completed, inactive, archived, import)
• <b>Legacy Support</b> - Added script to update legacy customers with missing location and is_guest fields"""
            },
            {
                "title": "Up to 2025-01-08",
                "content": """<b>User-Facing Updates</b>
• <b>Enhanced Offer Notifications</b> - Clickable offer links in group order announcements for quick access to offer details
• <b>Improved Order Display</b> - Chronological order listing in /offer_orders (oldest to newest) for better tracking
• <b>Cleaner Offer Announcements</b> - Removed capacity display from notifications, simplified to show only name and price
• <b>Improved Message Flow</b> - New offer announcements sent before images for clearer communication
• <b>Consistent Internationalization</b> - SOLD OUT status and order notifications now properly translated in group messages
• <b>Consistent Order Views</b> - Status headers always shown in /my_orders and /user_orders for clarity
• <b>Better Sold Out Detection</b> - Offers correctly transition between ACTIVE and SOLD_OUT based on actual capacity

<b>Admin-Facing Updates</b>
• <b>Modular Order Management</b> - Refactored 1000+-line order_commands.py files into focused modules (cancellation, placement, viewing, status, maintenance) for better maintainability
• <b>Comprehensive Test Coverage</b> - Added full test suite for refactored admin order handlers with test runner script
• <b>Performance Optimization</b> - Implemented comprehensive user caching system with smart invalidation, eliminating repeated DynamoDB scans
• <b>Reduced API Costs</b> - SSM parameter caching reduces repeated API calls across Lambda container reuse
• <b>Async Notification System</b> - Dedicated notification sender Lambda with 5-minute timeout prevents timeouts for large subscriber lists (scales to hundreds)
• <b>Smart Notification Routing</b> - Sync delivery for ≤10 subscribers, async for >10 with pre-generated S3 URLs
• <b>Better Wholesale Ordering</b> - Preserves existing ordered boxes during wholesale process, only updates non-ordered boxes
• <b>Improved Box Status Management</b> - Local box status updated after database changes for consistency
• <b>Single-Box Order Constraint</b> - Orders validated to fit within single boxes, preventing multi-box spanning
• <b>Enhanced Order Placement</b> - Admin orders from sold out offers now show clear sold out message with offer name
• <b>Consolidated Order Logic</b> - Refactored handle_confirm_order to reuse handle_order, eliminating ~40 lines of duplicate code
• <b>Better Offer Status Logic</b> - Fixed premature sold_out transitions, offers only marked sold out when boxes ordered AND no capacity
• <b>Consistent Customer Matching</b> - Extracted shared customer matching logic to ValidationUtils for single source of truth
• <b>Improved Internationalization</b> - Replaced hardcoded "Unknown" strings with i18n translation
• <b>Enhanced Debugging</b> - Detailed logging for Telegram token retrieval and SSM parameter access
• <b>Customer Management Tool</b> - New script to check customers against group members
• <b>Better Status Consistency</b> - Orders added to wholesale-ordered boxes now correctly show 'ordered' status"""
            },
            {
                "title": "Up to 2025-01-05",
                "content": """<b>User-Facing Updates</b>
• <b>Improved Order Management</b> - Added /delete_completed command to remove completed orders from personal register
• <b>Complete Order Visibility</b> - All order statuses now display properly including completed, ready_for_labeling, labeling_completed, and awaiting_payment
• <b>Better Status Display</b> - Improved status consistency with uppercase formatting and visual indicators (📦🍺) for ordered offers
• <b>Improved Internationalization</b> - Fewer hardcoded strings. Status icons (✅ ⚠️ ❌), and unit pluralization now use proper translation system
• <b>Enhanced Order Processing</b> - Orders prevented from spanning multiple boxes for simpler inventory management
• <b>Improved Wholesale Visibility</b> - All pending orders shown in wholesale summaries without artificial limits

<b>Admin-Facing Updates</b>
• <b>Enhanced Order Display</b> - Truncated order IDs to 8 characters in /my_orders for better readability
• <b>Enhanced Order Management</b> - Renamed /delete_old_cancelled to /delete_old to handle both cancelled and completed orders older than 7 days
• <b>Improved CSV Exports</b> - Added order status field to /all_orders CSV with streamlined column structure (removed username and box_id)
• <b>Better Order Cancellation</b> - Enhanced /cancel_order with customer name display, proper parameter handling, and comprehensive notifications
• <b>Advanced Wholesale Management</b> - Added "Complete Delivery" and "Complete Labeling" buttons for streamlined bulk processing with confirmation dialogs
• <b>Enhanced Order Processing</b> - FIFO (first-in-first-out) order processing ensures fair distribution in wholesale ordering
• <b>Improved Delivery Workflow</b> - Better box filtering showing 'ordered' status boxes, alphabetically sorted suppliers, and proper workflow continuation
• <b>Customer Data Enhancement</b> - Added default delivery location field to customer entity with default Venster, Utrecht (incomplete)
• <b>System Reliability</b> - Fixed parameter handling in notifications, customer lookup errors, database method calls, and callback validation
• <b>Better Admin Interface</b> - Enhanced admin panel with 🔄 Workflow button grouping core business process commands
• <b>Enhanced Offer Management</b> - New /delete_offer command for removing completed/inactive offers with proper status ordering
• <b>Improved Error Handling</b> - Fixed decimal conversion issues, missing translation keys, and parameter validation across all commands"""
            },
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
• <b>Offer Management Improvements</b> - Consolidated offer editing interface with full functionality in <code>/view_offer</code>
• <b>Edit Offer button</b> - Direct access from offer details view for quick editing
• <b>Seamless editing workflow</b> - Return to edit menu after field updates with maintained context
• <b>System Reliability</b> - Improved HTTP request handling with proper timeouts and better error handling
• <b>Modular service architecture</b> - Better maintainability with reduced code duplication and improved callback handling"""
            },
            {
                "title": "Up to 2025-12-25",
                "content": """<b>User-Facing Updates</b>
• <b>New /view_offer command</b> - View detailed offer information with images and descriptions
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