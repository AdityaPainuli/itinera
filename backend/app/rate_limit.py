"""Global daily request quota.

This is intentionally simple — one shared counter across all callers, since the
app is a single-tenant hobby deployment with no auth. The counter auto-resets
at the start of each UTC day. Manual reset (bumping the limit back up mid-day)
is done with a SQL update against the `rate_limits` table.

Concurrency: at hobby scale (~7 requests/day) we don't need row locks. A double-
spend race would let through 8 instead of 7. Acceptable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import RateLimitRow

_SINGLETON_ID = 1


@dataclass
class QuotaResult:
    allowed: bool
    count: int            # count *after* this attempt's increment (or current if denied)
    limit: int
    reset_at: datetime    # UTC timestamp when the period rolls over
    should_notify: bool   # True only on the request that *just* hit the limit

    @property
    def retry_after_seconds(self) -> int:
        delta = self.reset_at - datetime.utcnow()
        return max(1, int(delta.total_seconds()))


def _today_start_utc(now: datetime) -> datetime:
    return datetime(now.year, now.month, now.day)


async def check_and_consume(session: AsyncSession, limit: int) -> QuotaResult:
    """Check the quota and consume one slot if available.

    Best-effort, not strictly atomic — see the module docstring on concurrency.
    Returns a QuotaResult describing the outcome. The caller is responsible
    for raising 429 when `allowed=False` and firing the notification when
    `should_notify=True` (we keep IO out of the DB transaction).
    """
    now = datetime.utcnow()
    today = _today_start_utc(now)
    tomorrow = today + timedelta(days=1)

    row = await session.get(RateLimitRow, _SINGLETON_ID)
    if row is None:
        row = RateLimitRow(id=_SINGLETON_ID, count=0, period_start=today, notified_at=None)
        session.add(row)

    # Auto-reset at the UTC day boundary.
    if row.period_start < today:
        row.count = 0
        row.period_start = today
        row.notified_at = None

    if row.count >= limit:
        await session.commit()
        return QuotaResult(
            allowed=False,
            count=row.count,
            limit=limit,
            reset_at=tomorrow,
            should_notify=False,
        )

    row.count += 1
    just_hit = row.count >= limit and row.notified_at is None
    if just_hit:
        row.notified_at = now
    await session.commit()

    return QuotaResult(
        allowed=True,
        count=row.count,
        limit=limit,
        reset_at=tomorrow,
        should_notify=just_hit,
    )
