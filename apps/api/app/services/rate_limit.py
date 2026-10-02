from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import RateLimitEvent


def check_rate_limit(db: Session, key: str, limit: int, window_seconds: int) -> bool:
    """Record an attempt for `key` and report whether it is within `limit` per `window_seconds`.

    Returns True if the caller is within the allowed rate, False if the limit is exceeded.
    Stale events for this key (older than the window) are opportunistically pruned so the
    table doesn't grow unboundedly.
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(seconds=window_seconds)

    db.execute(
        delete(RateLimitEvent).where(
            RateLimitEvent.key == key, RateLimitEvent.created_at < window_start
        )
    )
    db.add(RateLimitEvent(key=key, created_at=now))
    db.flush()

    count = db.scalar(
        select(func.count())
        .select_from(RateLimitEvent)
        .where(RateLimitEvent.key == key, RateLimitEvent.created_at >= window_start)
    )
    # Commit here (rather than leaving it to the route handler) so the attempt is durably
    # recorded even when the caller aborts the request with a 429 before reaching its own commit.
    db.commit()
    return count <= limit
