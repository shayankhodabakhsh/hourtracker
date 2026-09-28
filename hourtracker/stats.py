"""Time math for study totals. Pure functions: no GTK, no database.

Timestamps are Unix seconds. Local dates come from naive datetimes, which
Python converts with the system time zone rules, so daylight-saving days
come out as 23 or 25 hours long.
"""
import calendar
import subprocess
from datetime import date, datetime, time, timedelta

MONDAY, SUNDAY = 0, 6


def local_midnight(d: date) -> float:
    """Unix time of 00:00 local time on date d."""
    return datetime.combine(d, time()).timestamp()


def local_date(ts: float) -> date:
    """Local calendar date of Unix time ts."""
    return datetime.fromtimestamp(ts).date()


def day_totals(sessions, first: date, days: int) -> list[float]:
    """Seconds studied on each of `days` local dates starting at `first`.

    `sessions` is an iterable of (start, end) pairs. A session that crosses
    midnight is split between the days; time outside the range is ignored.
    """
    edges = [local_midnight(first + timedelta(days=i)) for i in range(days + 1)]
    totals = [0.0] * days
    for start, end in sessions:
        for i in range(days):
            totals[i] += max(0.0, min(end, edges[i + 1]) - max(start, edges[i]))
    return totals


def week_start(d: date, first_weekday: int) -> date:
    """First day of the week containing d (first_weekday: 0=Monday ... 6=Sunday)."""
    return d - timedelta(days=(d.weekday() - first_weekday) % 7)


def add_months(d: date, n: int) -> date:
    """First day of the month that is n months after d's month."""
    index = d.year * 12 + d.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def period(view: str, anchor: date, first_weekday: int) -> tuple[date, int]:
    """(first day, number of days) of the "week" or "month" containing anchor."""
    if view == "week":
        return week_start(anchor, first_weekday), 7
    return anchor.replace(day=1), calendar.monthrange(anchor.year, anchor.month)[1]


def shift(view: str, anchor: date, steps: int) -> date:
    """Anchor moved by whole weeks or months (negative steps go back)."""
    if view == "week":
        return anchor + timedelta(weeks=steps)
    return add_months(anchor, steps)


def period_label(view: str, first: date, days: int) -> str:
    """'Sep 27 – Oct 3' for a week, 'September 2026' for a month."""
    if view == "month":
        return f"{first:%B %Y}"
    last = first + timedelta(days=days - 1)
    return f"{first:%b} {first.day} – {last:%b} {last.day}"


def fmt_clock(seconds: float) -> str:
    """Hours and minutes like '1:05', rounded down."""
    minutes = int(max(0.0, seconds) // 60)
    return f"{minutes // 60}:{minutes % 60:02d}"


def fmt_duration(seconds: float) -> str:
    """'2h 05m', '45m', or '0m', rounded down."""
    hours, minutes = divmod(int(max(0.0, seconds) // 60), 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def locale_first_weekday() -> int:
    """First weekday of the current LC_TIME locale (0=Monday ... 6=Sunday).

    glibc gives a reference date (week-1stday) and a 1-based offset from it
    (first_weekday). Falls back to Monday if `locale` can't be read.
    """
    try:
        out = subprocess.run(["locale", "week-1stday", "first_weekday"],
                             capture_output=True, text=True, timeout=2,
                             check=True).stdout.split()
        reference = datetime.strptime(out[0], "%Y%m%d").date()
        return (reference.weekday() + int(out[1]) - 1) % 7
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return MONDAY


def resolve_first_weekday(setting: str) -> int:
    """Map the week_start setting ('auto', 'sunday', 'monday') to a weekday."""
    if setting == "sunday":
        return SUNDAY
    if setting == "monday":
        return MONDAY
    return locale_first_weekday()
