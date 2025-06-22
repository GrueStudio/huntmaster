from fastapi.templating import Jinja2Templates
from datetime import datetime, UTC, timedelta
# Configure Jinja2Templates (assuming templates directory is relative to app root)
templates = Jinja2Templates(directory="templates")

def format_datetime_iso_utc(dt: datetime) -> str:
    """
    Formats a datetime object to 'YYYY-MM-DDTHH:MM:SSZ' (ISO 8601 UTC).
    This format is ideal for JavaScript Date parsing on the frontend.
    """
    if dt is None:
        return "N/A"
    # Ensure it's UTC and naive before formatting to ISO string with 'Z'
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


# Filter to format date only
def format_date_only(dt: datetime) -> str:
    """
    Formats a datetime object to 'YYYY-MM-DD' (date only).
    All times take place at server save (a general note for tooltips).
    """
    if dt is None:
        return "N/A"
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.strftime('%Y-%m-%d')

def durationformat(value: timedelta):
    if value is None:
        return "&infin;" # Changed to return "Infinity" when value is None
    total_seconds = int(value.total_seconds())
    days = total_seconds // (24 * 3600)
    total_seconds %= (24 * 3600)
    hours = total_seconds // 3600
    total_seconds %= 3600
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 or not parts: # Include seconds if there's nothing else, or if it's 0 seconds
        if not parts and seconds == 0: # Handle timedelta(0)
                return "0 minutes" # Or "0 seconds", depends on desired granularity
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    return " ".join(parts) if parts else "0 minutes" # Default for empty timedelta

# Filter to format duration in minutes to Hh:Mm
def format_duration(minutes: int) -> str:
    """
    Converts a duration in minutes to a string in 'Xh:Ym' format.
    If minutes is 0, returns '0m'.
    """
    if minutes is None:
        return "N/A"
    total_minutes = int(minutes)
    if total_minutes == 0:
        return "0m"
    hours = total_minutes // 60
    remaining_minutes = total_minutes % 60
    if hours > 0:
        return f"{hours}h:{remaining_minutes:02d}m"
    return f"{remaining_minutes}m"

# Register the custom filters
templates.env.filters['datetimeformat'] = format_datetime_iso_utc
templates.env.filters['dateformat'] = format_date_only
templates.env.filters['durationformat'] = format_duration
templates.env.filters['timedeltaformat'] = durationformat

templates.env.globals['now'] = datetime.utcnow
