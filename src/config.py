"""
Central configuration for UBBC Bot
"""
import os

# Admin user configuration
# REQUIRED: Set via environment variable ADMIN_USER_ID
ADMIN_USER_ID = int(os.environ.get('ADMIN_USER_ID', '0'))
    