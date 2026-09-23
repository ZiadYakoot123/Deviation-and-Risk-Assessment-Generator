from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


_TIMESTAMP_PATTERN = re.compile(r"(\d{8})[_-]?(\d{4})")


def extract_trend_time(trend_image_path: str) -> datetime:
    """Extract trend timestamp from image filename, e.g. trend_20260923_0930.png."""
    name = Path(trend_image_path).name
    match = _TIMESTAMP_PATTERN.search(name)
    if not match:
        raise ValueError("Unable to extract trend time from image name; include YYYYMMDD_HHMM")

    return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M")
