from datetime import UTC, datetime, timedelta

from app.models import RateLimitEvent
from app.services.rate_limit import check_rate_limit


def test_requests_within_limit_pass(db):
    for _ in range(10):
        assert check_rate_limit(db, "auth:1.1.1.1", limit=10, window_seconds=60) is True


def test_eleventh_request_in_window_is_rejected(db):
    for _ in range(10):
        assert check_rate_limit(db, "auth:1.1.1.1", limit=10, window_seconds=60) is True
    assert check_rate_limit(db, "auth:1.1.1.1", limit=10, window_seconds=60) is False


def test_different_keys_do_not_interfere(db):
    for _ in range(10):
        assert check_rate_limit(db, "auth:1.1.1.1", limit=10, window_seconds=60) is True
    # A different key starts with a fresh window even though the first is exhausted.
    assert check_rate_limit(db, "auth:2.2.2.2", limit=10, window_seconds=60) is True


def test_events_outside_window_do_not_count(db):
    stale_time = datetime.now(UTC) - timedelta(seconds=120)
    for _ in range(10):
        db.add(RateLimitEvent(key="auth:3.3.3.3", created_at=stale_time))
    db.commit()
    # All 10 prior events are outside the 60s window, so this request should still pass
    # and the stale rows should be pruned as a side effect.
    assert check_rate_limit(db, "auth:3.3.3.3", limit=10, window_seconds=60) is True

    remaining = db.query(RateLimitEvent).filter(RateLimitEvent.key == "auth:3.3.3.3").count()
    assert remaining == 1


def test_endpoint_rate_limits_across_requests(client):
    payload = {"email": "user@example.com", "password": "wrong-password-value"}
    for _ in range(10):
        response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 429
