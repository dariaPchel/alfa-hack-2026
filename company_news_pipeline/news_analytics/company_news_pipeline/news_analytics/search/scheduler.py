"""Daily scheduler for 06:00 Europe/Moscow per-ID 90/7-day refresh."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .worker import run_daily_refresh


def seconds_until_next_run(now: datetime | None = None) -> float:
    timezone = ZoneInfo(os.getenv("NEWS_ANALYTICS_SCHEDULE_TIMEZONE", "Europe/Moscow"))
    now = now.astimezone(timezone) if now else datetime.now(timezone)
    hour = max(0, min(23, int(os.getenv("NEWS_ANALYTICS_REFRESH_HOUR", "6"))))
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def main() -> None:
    while True:
        delay = seconds_until_next_run()
        print(f"Next company-news refresh in {int(delay)} seconds")
        time.sleep(delay)
        result = run_daily_refresh()
        print(f"Daily company-news refresh: {result['status']} ({result.get('company_count', 0)} companies)")


if __name__ == "__main__":
    main()
