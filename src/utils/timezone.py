from datetime import datetime, timezone, timedelta
from typing import Union
import zoneinfo

# Central European timezone (automatically handles CET/CEST)
CET = zoneinfo.ZoneInfo('Europe/Amsterdam')

# Month abbreviations for localization
MONTH_ABBR = {
    'en': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
    'nl': ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']
}

def to_cet_string(dt: Union[datetime, str], format_str: str = '%Y-%m-%d %H:%M') -> str:
    """Convert UTC datetime to CET/CEST timezone string (automatically handles DST)"""
    if isinstance(dt, str):
        # Parse ISO string and convert to CET/CEST
        utc_dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        cet_dt = utc_dt.astimezone(CET)
    else:
        # Convert datetime object to CET/CEST
        if dt.tzinfo is None:
            # Assume UTC if no timezone info
            utc_dt = dt.replace(tzinfo=timezone.utc)
        else:
            utc_dt = dt
        cet_dt = utc_dt.astimezone(CET)
    
    return cet_dt.strftime(format_str)

def to_cet_localized(dt: Union[datetime, str], locale: str = 'nl') -> str:
    """Convert UTC datetime to localized CET date string (d MMM yy format)"""
    if isinstance(dt, str):
        utc_dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        cet_dt = utc_dt.astimezone(CET)
    else:
        if dt.tzinfo is None:
            utc_dt = dt.replace(tzinfo=timezone.utc)
        else:
            utc_dt = dt
        cet_dt = utc_dt.astimezone(CET)
    
    month_abbr = MONTH_ABBR.get(locale, MONTH_ABBR['nl'])
    return f"{cet_dt.day} {month_abbr[cet_dt.month - 1]} {cet_dt.strftime('%y')}"