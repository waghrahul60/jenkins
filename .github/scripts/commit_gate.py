#!/usr/bin/env python3
"""
commit_gate.py
──────────────
Decides whether the GitHub Actions runner should commit right now.

Rules
─────
  • Only Mon–Fri are ever active (Sat/Sun always skip).
  • Every week has exactly 1 random break day  (Mon–Fri).
  • 6–7 randomly chosen weeks per year get 2 break days instead of 1.
  • Within an active day, not every hourly trigger commits — a per-hour
    coin flip (≈60 % chance) keeps the cadence organic.

Randomness strategy
───────────────────
All randomness is seeded deterministically from (year, ISO-week-number)
so every workflow run within the same week agrees on which days are breaks,
with no external state file required.

Exit codes
──────────
  0 → proceed with commit
  1 → skip (break day, weekend, or hourly coin flip)
"""

import sys
import os
import random
import datetime
import zoneinfo


IST = zoneinfo.ZoneInfo("Asia/Kolkata")

# Weekday indices (Monday = 0 … Sunday = 6)
WEEKDAYS = list(range(5))   # Mon–Fri = 0..4

# Fraction of hours that actually trigger a commit (keeps cadence organic)
HOURLY_COMMIT_PROBABILITY = 0.60

# How many weeks per year get 2 break days instead of 1
DOUBLE_BREAK_WEEKS_MIN = 6
DOUBLE_BREAK_WEEKS_MAX = 7


def _year_rng(year: int) -> random.Random:
    """RNG seeded by year — used to pick which weeks are 'double-break' weeks."""
    return random.Random(year * 31337)


def _week_rng(year: int, week: int) -> random.Random:
    """RNG seeded by (year, week) — used to pick break days within a week."""
    return random.Random(year * 1000 + week)


def _hour_rng(year: int, week: int, day_of_year: int, hour: int) -> random.Random:
    """RNG seeded by (year, week, day, hour) — hourly coin flip."""
    return random.Random(year * 10_000_000 + week * 100_000 + day_of_year * 100 + hour)


def get_double_break_weeks(year: int) -> set[int]:
    """Return the set of ISO week numbers that have 2 break days this year."""
    rng = _year_rng(year)
    count = rng.randint(DOUBLE_BREAK_WEEKS_MIN, DOUBLE_BREAK_WEEKS_MAX)
    # ISO weeks in a year are 1..52 (sometimes 53; clamp to 52 for simplicity)
    return set(rng.sample(range(1, 53), count))


def get_break_days(year: int, week: int) -> set[int]:
    """Return the set of weekday indices (0=Mon … 4=Fri) that are break days."""
    double_weeks = get_double_break_weeks(year)
    num_breaks = 2 if week in double_weeks else 1

    rng = _week_rng(year, week)
    return set(rng.sample(WEEKDAYS, num_breaks))


def should_commit(now: datetime.datetime | None = None) -> tuple[bool, str]:
    """
    Return (go, reason).
    go=True  → commit this run
    go=False → skip this run
    """
    if now is None:
        now = datetime.datetime.now(tz=IST)

    # Whether the workflow was triggered manually or by cron
    is_manual = os.environ.get("TRIGGER_EVENT", "schedule") == "workflow_dispatch"

    iso_year, iso_week, _ = now.isocalendar()
    weekday = now.weekday()   # 0=Mon … 6=Sun

    # ── Weekend check (skip only for scheduled/auto runs) ──────────────────
    if weekday > 4 and not is_manual:
        return False, f"Weekend ({now.strftime('%A')}) — skipping (auto run)"
    elif weekday > 4 and is_manual:
        return True, f"Weekend ({now.strftime('%A')}) — allowed because manually triggered"

    # ── Break-day check ───────────────────────────────────────────────────
    break_days = get_break_days(iso_year, iso_week)
    if weekday in break_days:
        day_name = ["Mon", "Tue", "Wed", "Thu", "Fri"][weekday]
        double_weeks = get_double_break_weeks(iso_year)
        break_count = 2 if iso_week in double_weeks else 1
        return False, (
            f"Break day: {day_name} is one of {break_count} break day(s) "
            f"for week {iso_week}/{iso_year}"
        )

    # ── Hourly coin flip ──────────────────────────────────────────────────
    doy = now.timetuple().tm_yday
    rng = _hour_rng(iso_year, iso_week, doy, now.hour)
    if rng.random() >= HOURLY_COMMIT_PROBABILITY:
        return False, (
            f"Hourly skip ({now.strftime('%H:00 IST')}) — "
            f"organic cadence randomiser said no"
        )

    return True, f"GO — committing at {now.strftime('%Y-%m-%d %H:%M IST')}"


def main() -> None:
    go, reason = should_commit()
    print(reason)
    sys.exit(0 if go else 1)


if __name__ == "__main__":
    main()
