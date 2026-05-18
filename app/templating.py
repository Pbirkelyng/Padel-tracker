from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def format_datetime(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%a %d %b %Y, %H:%M")


def format_date(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d")


def format_time(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%H:%M")


templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_date"] = format_date
templates.env.filters["format_time"] = format_time

