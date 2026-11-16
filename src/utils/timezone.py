import zoneinfo
from datetime import UTC, datetime

# Central European timezone (automatically handles CET/CEST)
CET = zoneinfo.ZoneInfo("Europe/Amsterdam")

# Month abbreviations for localization
MONTH_ABBR = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "nl": ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"],
}


def to_utc_datetime(value: datetime | str | None) -> datetime:
    """A timezone-aware UTC datetime from what the bot stores: an ISO string or a datetime (naive means UTC).

    A missing or unreadable value gives the earliest possible moment, so such an item sorts before real dates
    and a list can be sorted without a TypeError between naive and aware values.
    """
    earliest = datetime.min.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return earliest
    if not isinstance(value, datetime):
        return earliest
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(UTC)


def to_cet_string(dt: datetime | str, format_str: str = "%Y-%m-%d %H:%M") -> str:
    """Convert UTC datetime to CET/CEST timezone string (automatically handles DST)"""
    if isinstance(dt, str):
        # Parse ISO string and convert to CET/CEST
        utc_dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        cet_dt = utc_dt.astimezone(CET)
    else:
        # Convert datetime object to CET/CEST (assume UTC if no timezone info)
        utc_dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
        cet_dt = utc_dt.astimezone(CET)

    return cet_dt.strftime(format_str)


def to_cet_localized(dt: datetime | str, locale: str = "nl") -> str:
    """Convert UTC datetime to localized CET date string (d MMM yy format)"""
    if isinstance(dt, str):
        utc_dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        cet_dt = utc_dt.astimezone(CET)
    else:
        utc_dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
        cet_dt = utc_dt.astimezone(CET)

    month_abbr = MONTH_ABBR.get(locale, MONTH_ABBR["nl"])
    return f"{cet_dt.day} {month_abbr[cet_dt.month - 1]} {cet_dt.strftime('%y')}"
