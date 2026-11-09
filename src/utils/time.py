# src/utils/time.py
"""
Timestamp normaliser used by ingestion pipelines.

Accepts the four feed‑format examples used in the project
and returns **both** an ISO‑8601 UTC string (YYYY‑MM‑DDTHH:MM:SSZ)
and a Unix epoch integer (seconds since 1970‑01‑01 UTC).
"""

from __future__ import annotations

import calendar
import re
from datetime import datetime, timezone

_UTC = timezone.utc  # Python 3.9-compatible UTC sentinel


# ----------------------------------------------------------------------
# Helper – parse any ISO‑8601 string (with Z or +/- offset) to a UTC datetime
# ----------------------------------------------------------------------
def _parse_iso(ts: str) -> datetime:
    """Convert an ISO‑8601 string to a timezone‑aware datetime in UTC.

    Accepts ``2024-07-03T14:52:31Z`` as well as
    ``2024-07-03T14:52:31+00:00``.
    """
    # ``datetime.fromisoformat`` does not understand trailing ``Z``,
    # so replace it with ``+00:00`` first.
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.astimezone(_UTC)


# ----------------------------------------------------------------------
# Main public function
# ----------------------------------------------------------------------
def normalize_timestamp(ts: str) -> tuple[str, int]:
    """Parse *any* of the four supported raw timestamp formats and return:

    * ``iso_utc`` – ``YYYY‑MM‑DDTHH:MM:SSZ`` (always UTC)
    * ``epoch``   – integer Unix epoch seconds

    Raises:
        ValueError: if the input does not match any known format.
    """
    ts = ts.strip()
    if ts.endswith(" UTC"):
        ts = ts[:-4] + "Z"

    # 1️⃣ URLhaus / OTX – pure ISO‑8601 (Z or +/- offset)
    try:
        dt = _parse_iso(ts)
    except ValueError:
        pass
    else:
        epoch = int(dt.timestamp())
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), epoch

    # 2️⃣ ThreatFox – space‑separated without timezone, assume UTC
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", ts):
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=_UTC)
        epoch = int(dt.timestamp())
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), epoch

    # 3️⃣ MalwareBazaar – space‑separated with explicit offset (+00:00, etc.)
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S%z")
    except ValueError:
        pass
    else:
        dt = dt.astimezone(_UTC)
        epoch = calendar.timegm(dt.utctimetuple())
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), epoch

    # If we reach here the format is unsupported
    raise ValueError(f"Unsupported timestamp format: {ts!r}")
