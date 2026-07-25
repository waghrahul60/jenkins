#!/usr/bin/env python3
"""
commit_gate.py
──────────────
Decides whether the GitHub Actions runner should commit right now.

Rules
─────
  • Only Mon–Fri are ever active for scheduled runs (Sat/Sun skip).
  • Every week has exactly 1 random break day (Mon–Fri).
  • 6–7 randomly chosen weeks per year get 2 break days instead of 1.
  • Each active day is assigned a commit count deterministically:
      1 commit  → 50 % of days
      2 commits → 30 % of days
      3 commits → 20 % of days
  • The commit count determines how many specific hours are chosen from the
    9 AM–10 PM IST window. The gate passes only when the current hour is
    one of those chosen hours.

Randomness strategy
───────────────────
All randomness uses deterministic seeds derived from (year, ISO-week, day-of-year)
so every workflow run within the same day agrees on commit hours — no external
state file required.

Exit codes
──────────
  0 → proceed with commit
  1 → skip (break day, weekend, or not a scheduled commit hour)
"""

import sys
import os
import random
import datetime
import zoneinfo


IST = zoneinfo.ZoneInfo("Asia/Kolkata")

# Weekday indices (Monday = 0 … Sunday = 6)
WEEKDAYS = list(range(5))   # Mon–Fri = 0..4

# Active commit hours: 9 AM to 10 PM IST (cron fires at :30 each hour)
COMMIT_HOURS = list(range(9, 23))   # 9, 10, 11 … 22

# How many weeks per year get 2 break days instead of 1
DOUBLE_BREAK_WEEKS_MIN = 6
DOUBLE_BREAK_WEEKS_MAX = 7

# Daily commit count probabilities: (count, cumulative_threshold)
#   1 commit  50 %  → roll < 0.50
#   2 commits 30 %  → 0.50 ≤ roll < 0.80
#   3 commits 20 %  → roll ≥ 0.80
COMMIT_COUNT_THRESHOLDS = [(1, 0.50), (2, 0.80), (3, 1.01)]


# ─── RNG helpers ─────────────────────────────────────────────────────────────

def _year_rng(year: int) -> random.Random:
    """RNG seeded by year — picks which weeks are 'double-break' weeks."""
    return random.Random(year * 31337)


def _week_rng(year: int, week: int) -> random.Random:
    """RNG seeded by (year, week) — picks break days within a week."""
    return random.Random(year * 1000 + week)


def _day_rng(year: int, doy: int) -> random.Random:
    """RNG seeded by (year, day-of-year) — picks commit count & hours for a day."""
    return random.Random(year * 10_000 + doy * 97 + 13)


# ─── Break-day logic ─────────────────────────────────────────────────────────

def get_double_break_weeks(year: int) -> set[int]:
    """Return ISO week numbers that have 2 break days this year."""
    rng = _year_rng(year)
    count = rng.randint(DOUBLE_BREAK_WEEKS_MIN, DOUBLE_BREAK_WEEKS_MAX)
    return set(rng.sample(range(1, 53), count))


def get_break_days(year: int, week: int) -> set[int]:
    """Return weekday indices (0=Mon … 4=Fri) that are break days this week."""
    double_weeks = get_double_break_weeks(year)
    num_breaks = 2 if week in double_weeks else 1
    rng = _week_rng(year, week)
    return set(rng.sample(WEEKDAYS, num_breaks))


# ─── Daily commit schedule ────────────────────────────────────────────────────

def get_daily_commit_count(year: int, doy: int) -> int:
    """
    Return how many commits are scheduled for this day.
      1 commit  → 50 %
      2 commits → 30 %
      3 commits → 20 %
    Uses a separate RNG seed from the hour-picker so counts and hours are independent.
    """
    rng = _day_rng(year, doy)
    roll = rng.random()
    for count, threshold in COMMIT_COUNT_THRESHOLDS:
        if roll < threshold:
            return count
    return 1   # fallback


def get_commit_hours(year: int, doy: int, count: int) -> set[int]:
    """
    Pick `count` unique hours (from COMMIT_HOURS = 9–22 IST) for today's commits.
    Uses a second draw from the same day RNG so it's independent of count selection.
    """
    rng = _day_rng(year, doy)
    rng.random()   # consume the count-roll so hour picks use a different state
    return set(rng.sample(COMMIT_HOURS, count))


# ─── Main gate decision ───────────────────────────────────────────────────────

def should_commit(now: datetime.datetime | None = None) -> tuple[bool, str]:
    """
    Return (go, reason).
    go=True  → proceed with commit
    go=False → skip this run
    """
    if now is None:
        now = datetime.datetime.now(tz=IST)

    iso_year, iso_week, _ = now.isocalendar()
    weekday = now.weekday()   # 0=Mon … 6=Sun
    doy     = now.timetuple().tm_yday

    # ── Weekend check ─────────────────────────────────────────────────────
    if weekday > 4:
        return False, f"Weekend ({now.strftime('%A')}) — skipping (auto run)"

    # ── Break-day check ───────────────────────────────────────────────────
    break_days = get_break_days(iso_year, iso_week)
    if weekday in break_days:
        day_name   = ["Mon", "Tue", "Wed", "Thu", "Fri"][weekday]
        double_wks = get_double_break_weeks(iso_year)
        n_breaks   = 2 if iso_week in double_wks else 1
        return False, (
            f"Break day: {day_name} is one of {n_breaks} break day(s) "
            f"for week {iso_week}/{iso_year}"
        )

    # ── Daily commit schedule (count + specific hours) ────────────────────
    count        = get_daily_commit_count(iso_year, doy)
    commit_hours = get_commit_hours(iso_year, doy, count)

    if now.hour not in commit_hours:
        return False, (
            f"Not a commit hour ({now.hour:02d}:00 IST) — "
            f"today has {count} commit(s) scheduled at "
            f"{sorted(commit_hours)} IST"
        )

    return True, (
        f"GO — committing at {now.strftime('%Y-%m-%d %H:%M IST')} "
        f"(day has {count} commit(s) at hours {sorted(commit_hours)} IST)"
    )


def main() -> None:
    go, reason = should_commit()
    print(reason)
    sys.exit(0 if go else 1)


if __name__ == "__main__":
    main()
