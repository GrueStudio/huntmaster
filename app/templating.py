from fastapi.templating import Jinja2Templates
from datetime import datetime, UTC
# Configure Jinja2Templates (assuming templates directory is relative to app root)
templates = Jinja2Templates(directory="templates")

def datetimeformat(value, format="%b %d, %H:%M"):
    if isinstance(value, datetime):
        # Ensure the datetime object is timezone-aware (UTC) before formatting
        # or convert to naive UTC if it's already UTC
        if value.tzinfo is not None:
            utc_dt = value.astimezone(UTC)
        else:
            # Assume naive datetime objects passed from Python are already UTC
            # for consistent handling before conversion to ISO format.
            utc_dt = value.replace(tzinfo=UTC)

        # Format the UTC datetime to ISO 8601 string for data-utc-time attribute
        iso_utc_string = utc_dt.isoformat().replace('+00:00', 'Z')

        # Format the display text (which will be replaced by JS)
        display_text = utc_dt.strftime(format)

        # Return an HTML span tag that localizetime.js will process
        return f'<span class="local-datetime" data-utc-time="{iso_utc_string}">{display_text}</span>'
    return str(value) # Return string representation for non-datetime values

templates.env.filters['datetimeformat'] = datetimeformat
