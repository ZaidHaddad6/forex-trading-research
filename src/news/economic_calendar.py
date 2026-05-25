"""
High-impact economic calendar for 2026.
Checked before every trade to block entries around major events.

Block windows:
  Central bank rate decisions  → 4 hours before + 1 hour after
  CPI / NFP / GDP data         → 2 hours before + 1 hour after
"""
from datetime import datetime, timezone
from typing import Optional

_U = timezone.utc

# (event_datetime_utc, block_before_hours, label, affected_currencies)
EVENTS: list[tuple[datetime, float, str, list[str]]] = [

    # ── FOMC rate decisions (18:00 UTC) ────────────────────────────────
    (datetime(2026,  6, 10, 18, 0, tzinfo=_U), 4, "FOMC Rate Decision",  ["USD"]),
    (datetime(2026,  7, 29, 18, 0, tzinfo=_U), 4, "FOMC Rate Decision",  ["USD"]),
    (datetime(2026,  9, 16, 18, 0, tzinfo=_U), 4, "FOMC Rate Decision",  ["USD"]),
    (datetime(2026, 10, 28, 18, 0, tzinfo=_U), 4, "FOMC Rate Decision",  ["USD"]),
    (datetime(2026, 12,  9, 18, 0, tzinfo=_U), 4, "FOMC Rate Decision",  ["USD"]),

    # ── ECB rate decisions (12:15 UTC) ──────────────────────────────────
    (datetime(2026,  6, 11, 12, 15, tzinfo=_U), 4, "ECB Rate Decision",  ["EUR"]),
    (datetime(2026,  7, 23, 12, 15, tzinfo=_U), 4, "ECB Rate Decision",  ["EUR"]),
    (datetime(2026,  9, 10, 12, 15, tzinfo=_U), 4, "ECB Rate Decision",  ["EUR"]),
    (datetime(2026, 10, 29, 12, 15, tzinfo=_U), 4, "ECB Rate Decision",  ["EUR"]),
    (datetime(2026, 12, 17, 12, 15, tzinfo=_U), 4, "ECB Rate Decision",  ["EUR"]),

    # ── Bank of England decisions (12:00 UTC) ───────────────────────────
    (datetime(2026,  6, 18, 12,  0, tzinfo=_U), 4, "BOE Rate Decision",  ["GBP"]),
    (datetime(2026,  8,  6, 12,  0, tzinfo=_U), 4, "BOE Rate Decision",  ["GBP"]),
    (datetime(2026,  9, 17, 12,  0, tzinfo=_U), 4, "BOE Rate Decision",  ["GBP"]),
    (datetime(2026, 11,  5, 12,  0, tzinfo=_U), 4, "BOE Rate Decision",  ["GBP"]),
    (datetime(2026, 12, 17, 12,  0, tzinfo=_U), 4, "BOE Rate Decision",  ["GBP"]),

    # ── Bank of Japan decisions (~03:00 UTC day 2 of meeting) ───────────
    (datetime(2026,  6, 17,  3,  0, tzinfo=_U), 4, "BOJ Rate Decision",  ["JPY"]),
    (datetime(2026,  7, 31,  3,  0, tzinfo=_U), 4, "BOJ Rate Decision",  ["JPY"]),
    (datetime(2026,  9, 19,  3,  0, tzinfo=_U), 4, "BOJ Rate Decision",  ["JPY"]),
    (datetime(2026, 10, 29,  3,  0, tzinfo=_U), 4, "BOJ Rate Decision",  ["JPY"]),
    (datetime(2026, 12, 19,  3,  0, tzinfo=_U), 4, "BOJ Rate Decision",  ["JPY"]),

    # ── US CPI (12:30 UTC) ──────────────────────────────────────────────
    (datetime(2026,  6, 10, 12, 30, tzinfo=_U), 2, "US CPI Release",     ["USD"]),
    (datetime(2026,  7, 15, 12, 30, tzinfo=_U), 2, "US CPI Release",     ["USD"]),
    (datetime(2026,  8, 12, 12, 30, tzinfo=_U), 2, "US CPI Release",     ["USD"]),
    (datetime(2026,  9, 10, 12, 30, tzinfo=_U), 2, "US CPI Release",     ["USD"]),
    (datetime(2026, 10, 14, 12, 30, tzinfo=_U), 2, "US CPI Release",     ["USD"]),
    (datetime(2026, 11, 12, 12, 30, tzinfo=_U), 2, "US CPI Release",     ["USD"]),
    (datetime(2026, 12, 10, 12, 30, tzinfo=_U), 2, "US CPI Release",     ["USD"]),

    # ── US NFP / Non-Farm Payrolls (12:30 UTC, first Friday of month) ───
    (datetime(2026,  6,  5, 12, 30, tzinfo=_U), 2, "US NFP",             ["USD"]),
    (datetime(2026,  7,  2, 12, 30, tzinfo=_U), 2, "US NFP",             ["USD"]),
    (datetime(2026,  8,  7, 12, 30, tzinfo=_U), 2, "US NFP",             ["USD"]),
    (datetime(2026,  9,  4, 12, 30, tzinfo=_U), 2, "US NFP",             ["USD"]),
    (datetime(2026, 10,  2, 12, 30, tzinfo=_U), 2, "US NFP",             ["USD"]),
    (datetime(2026, 11,  6, 12, 30, tzinfo=_U), 2, "US NFP",             ["USD"]),
    (datetime(2026, 12,  4, 12, 30, tzinfo=_U), 2, "US NFP",             ["USD"]),

    # ── UK CPI (07:00 UTC, ~mid-month) ─────────────────────────────────
    (datetime(2026,  6, 17,  7,  0, tzinfo=_U), 2, "UK CPI Release",     ["GBP"]),
    (datetime(2026,  7, 15,  7,  0, tzinfo=_U), 2, "UK CPI Release",     ["GBP"]),
    (datetime(2026,  8, 19,  7,  0, tzinfo=_U), 2, "UK CPI Release",     ["GBP"]),
    (datetime(2026,  9, 16,  7,  0, tzinfo=_U), 2, "UK CPI Release",     ["GBP"]),
    (datetime(2026, 10, 14,  7,  0, tzinfo=_U), 2, "UK CPI Release",     ["GBP"]),
    (datetime(2026, 11, 18,  7,  0, tzinfo=_U), 2, "UK CPI Release",     ["GBP"]),
    (datetime(2026, 12, 16,  7,  0, tzinfo=_U), 2, "UK CPI Release",     ["GBP"]),

    # ── Japan CPI (~23:30 UTC night before release) ─────────────────────
    (datetime(2026,  6, 18, 23, 30, tzinfo=_U), 2, "Japan CPI Release",  ["JPY"]),
    (datetime(2026,  7, 23, 23, 30, tzinfo=_U), 2, "Japan CPI Release",  ["JPY"]),
    (datetime(2026,  8, 20, 23, 30, tzinfo=_U), 2, "Japan CPI Release",  ["JPY"]),
    (datetime(2026,  9, 17, 23, 30, tzinfo=_U), 2, "Japan CPI Release",  ["JPY"]),
    (datetime(2026, 10, 22, 23, 30, tzinfo=_U), 2, "Japan CPI Release",  ["JPY"]),
    (datetime(2026, 11, 19, 23, 30, tzinfo=_U), 2, "Japan CPI Release",  ["JPY"]),
    (datetime(2026, 12, 17, 23, 30, tzinfo=_U), 2, "Japan CPI Release",  ["JPY"]),
]


def _currencies_for_epic(epic: str) -> list[str]:
    known = ["EUR", "GBP", "JPY", "USD", "CHF", "AUD", "CAD", "NZD"]
    return [c for c in known if c in epic.upper()]


def get_blocks(epic: str, now: Optional[datetime] = None) -> list[str]:
    """Return event names currently blocking a trade on this epic.

    Returns an empty list when it is safe to trade.
    """
    if now is None:
        now = datetime.now(_U)

    currencies = _currencies_for_epic(epic)
    blocked = []

    for event_time, block_hours, label, affected in EVENTS:
        if not any(c in affected for c in currencies):
            continue
        hours_until = (event_time - now).total_seconds() / 3600
        # Block window: [block_hours before event] to [1 hour after]
        if -1.0 <= hours_until <= block_hours:
            tag = "in {:.0f}m".format(hours_until * 60) if hours_until > 0 else "active now"
            blocked.append(f"{label} ({tag})")

    return blocked
