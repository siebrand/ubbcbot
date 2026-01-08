# Guest User Feature

## Overview
The guest user feature allows admins to create and manage users who are not on Telegram, enabling centralized order management for all customers regardless of their Telegram status.

## Implementation

### Guest User Characteristics
- **Telegram ID**: Special format `GUEST_001`, `GUEST_002`, etc. (sequential numbering)
- **Status**: Automatically set to `APPROVED`
- **Language**: Defaults to Dutch (`nl`)
- **Guest Flag**: `is_guest: true` in database
- **Contact Info**: Optional field for email/phone
- **No Username**: Guest users have no Telegram username

### Commands

#### Admin Commands
- `/add_guest <first_name> [last_name] [contact]` - Create new guest user
  - Example: `/add_guest John Doe john@example.com`
  - Example: `/add_guest Jane` (minimal)
  - Example: `/add_guest Bob Smith 06-12345678`

- `/list_guests` - View all guest users (paginated)
  - Shows guest ID, name, and contact info
  - Paginated display (20 per page)

#### Existing Commands That Work With Guests
- `/update_user <guest_id> <new_first_name> [new_last_name]` - Update guest name
- `/update_user_first_name <customer_id> <new_first_name>` - Update first name
- `/update_user_last_name <customer_id> <new_last_name>` - Update last name
- `/order_for <guest_id> <offer_id> [quantity]` - Place order for guest
- `/user_orders <guest_id>` - View guest's orders
- `/cancel_order <order_id>` - Cancel guest order
- `/list_users` - Guests appear with 🎫 indicator

### Display Features
- Guest users shown with 🎫 emoji in user lists
- Guest ID displayed instead of username (e.g., `GUEST_001`)
- Contact info displayed in delivery overviews if present
- All existing order management workflows support guests

### Database Schema
```python
@dataclass
class Customer:
    telegram_user_id: str  # "GUEST_001" for guests, int for regular users
    is_guest: bool = False
    contact_info: Optional[str] = None
    # ... other fields
```

### Use Cases

1. **Family/Friends Without Telegram**
   - Admin creates guest user for family member
   - Places orders on their behalf
   - Tracks orders centrally

2. **Business Customers**
   - Create guest for local business
   - Store contact email/phone
   - Manage bulk orders

3. **Event Orders**
   - Create temporary guests for event attendees
   - Centralized order management
   - Easy cleanup after event

### Workflow Example

```bash
# Admin creates guest user
/add_guest Maria Garcia maria@email.com

# Response: ✅ Guest user added: Maria Garcia (GUEST_001)
# Contact: maria@email.com

# Admin places order for guest
/order_for GUEST_001 42 2

# Admin views guest orders
/user_orders GUEST_001

# Admin updates guest info if needed
/update_user GUEST_001 Maria Garcia-Lopez
```

### Integration Points

All existing features work seamlessly with guest users:
- ✅ Order placement and tracking
- ✅ Order cancellation
- ✅ Delivery overviews
- ✅ Payment tracking
- ✅ CSV exports
- ✅ User management commands

### Translation Keys

**English:**
- `usage_add_guest`: "Usage: /add_guest <first_name> [last_name] [contact]"
- `guest_added`: "✅ Guest user added: {name} ({guest_id}){contact}"
- `failed_add_guest`: "❌ Failed to add guest user"
- `no_guests`: "No guest users found"

**Dutch:**
- `usage_add_guest`: "Gebruik: /add_guest <voornaam> [achternaam] [contact]"
- `guest_added`: "✅ Gastgebruiker toegevoegd: {name} ({guest_id}){contact}"
- `failed_add_guest`: "❌ Kon gastgebruiker niet toevoegen"
- `no_guests`: "Geen gastgebruikers gevonden"

### Future Enhancements (Optional)

Potential future additions:
- `/delete_guest <guest_id>` - Delete guest with no orders
- `/update_guest_contact <guest_id> <contact>` - Update contact separately
- Email notifications for guests (if contact email provided)
- Convert guest to regular user if they join Telegram
