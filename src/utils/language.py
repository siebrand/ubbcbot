def detect_user_language(telegram_user_data: dict) -> str:
    """Detect user language from Telegram user data"""
    # Get language_code from Telegram user data
    language_code = telegram_user_data.get('language_code', '').lower()
    
    # Map common language codes to supported languages
    if language_code.startswith('nl'):
        return 'nl'
    elif language_code.startswith('en'):
        return 'en'
    
    # Default to Dutch for UBBC users
    return 'nl'