"""Is the tutorial's real-world data still current?

Run `python freshness.py`. It flags prices older than pricing.PRICES_MAX_AGE_DAYS
and dates in pricing.WATCH_DATES that are coming up or have passed since the
prices were last checked. Exit code 1 means something needs a look; the monthly
CI workflow turns that report into a GitHub issue.
"""

import sys
from collections.abc import Iterable
from datetime import date

import pricing

HEADS_UP_DAYS = 14


def check(today: date, last_checked: str, watch_dates: Iterable[tuple[str, str]], max_age_days: int) -> list[str]:
    checked = date.fromisoformat(last_checked)
    items = []
    age = (today - checked).days
    if age > max_age_days:
        items.append(
            f"Prices were last checked {age} days ago ({last_checked}); re-verify them (limit: {max_age_days} days)."
        )
    for when, what in watch_dates:
        event = date.fromisoformat(when)
        if today < event <= date.fromordinal(today.toordinal() + HEADS_UP_DAYS):
            items.append(f"Coming up on {when} (in {(event - today).days} days): {what}")
        elif checked < event <= today:
            items.append(f"Happened on {when}, after prices were last checked ({last_checked}): {what}")
    return items


def main(today: date | None = None) -> int:
    items = check(today or date.today(), pricing.LAST_CHECKED, pricing.WATCH_DATES, pricing.PRICES_MAX_AGE_DAYS)
    if not items:
        print(f"All current: prices checked {pricing.LAST_CHECKED}, no watched dates due.")
        return 0
    print("## Needs attention\n")
    print("\n".join(f"- {item}" for item in items))
    print("\n## How to re-verify\n")
    print("Check each page, update `pricing.py`, and bump `LAST_CHECKED`:\n")
    print("\n".join(f"- {name}: {url}" for name, url in pricing.SOURCES.items()))
    return 1


if __name__ == "__main__":
    sys.exit(main())
