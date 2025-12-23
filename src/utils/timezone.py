from datetime import datetime, timezone, timedelta
from typing import Union
import zoneinfo

# Central European timezone (automatically handles CET/CEST)
CET = zoneinfo.ZoneInfo('Europe/Amsterdam')

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