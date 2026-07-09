import stripe
from conftest import pending_order

from app.config import get_settings
from app.models import InventoryMovement, OrderStatus, PaymentStatus, ProcessedWebhook


def _use_webhook_secret(client, secret="whsec_test_secret"):
    """Override the settings dependency so the endpoint requires/accepts a secret
    without depending on the module-level lru_cache in app.config.get_settings.
    """
    from app.main import app

    settings = get_settings().model_copy(update={"stripe_webhook_secret": secret})
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


def fake_event(event_id, event_type, order_id):
    # Real Stripe metadata values are always strings, so mirror that here:
    # app/api.py's stripe_webhook coerces the metadata string to uuid.UUID
    # itself before calling db.get(Order, ...).
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": {"metadata": {"order_id": str(order_id)}}},
    }


def test_webhook_without_signature_header_is_rejected(client):
    response = client.post("/api/v1/stripe/webhook", content=b"{}")
    assert response.status_code == 400


def test_webhook_without_configured_secret_is_rejected(client):
    # Default test settings have no stripe_webhook_secret configured, so even a
    # signature header present should be rejected before signature verification.
    response = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=deadbeef"},
    )
    assert response.status_code == 400


def test_webhook_invalid_signature_is_rejected(client):
    _use_webhook_secret(client)
    response = client.post(
        "/api/v1/stripe/webhook",
        content=b'{"id": "evt_bad"}',
        headers={"Stripe-Signature": "t=1,v1=not-a-real-signature"},
    )
    assert response.status_code == 400


def test_valid_checkout_completed_marks_order_paid_and_decrements_stock_once(
    client, db, monkeypatch
):
    _use_webhook_secret(client)
    order, variant = pending_order(db)
    event = fake_event("evt_completed_1", "checkout.session.completed", order.id)
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    response = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=whatever"},
    )
    assert response.status_code == 204

    db.refresh(order)
    db.refresh(variant)
    assert order.status == OrderStatus.PAID
    assert order.payment.status == PaymentStatus.SUCCEEDED
    assert variant.stock_on_hand == 2  # 4 - 2, decremented exactly once
    assert variant.stock_reserved == 0
    assert (
        db.query(InventoryMovement)
        .filter_by(reason="payment_succeeded", reference=str(order.id))
        .count()
        == 1
    )
    assert db.get(ProcessedWebhook, event["id"]) is not None


def test_replaying_same_event_id_is_a_no_op(client, db, monkeypatch):
    _use_webhook_secret(client)
    order, variant = pending_order(db)
    event = fake_event("evt_completed_replay", "checkout.session.completed", order.id)
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    first = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=whatever"},
    )
    assert first.status_code == 204

    second = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=whatever"},
    )
    assert second.status_code == 204

    db.refresh(order)
    db.refresh(variant)
    assert order.status == OrderStatus.PAID
    assert variant.stock_on_hand == 2
    assert variant.stock_reserved == 0
    assert (
        db.query(InventoryMovement)
        .filter_by(reason="payment_succeeded", reference=str(order.id))
        .count()
        == 1
    )
    assert db.query(ProcessedWebhook).filter_by(event_id=event["id"]).count() == 1


def test_webhook_sends_one_email_and_replay_does_not_resend(client, db, monkeypatch):
    import app.api as api_module

    _use_webhook_secret(client)
    order, variant = pending_order(db)
    event = fake_event("evt_completed_email", "checkout.session.completed", order.id)
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    sent = []
    monkeypatch.setattr(
        api_module, "send_order_confirmation", lambda order, s=None: sent.append(order.id)
    )

    first = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=whatever"},
    )
    assert first.status_code == 204
    assert len(sent) == 1

    second = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=whatever"},
    )
    assert second.status_code == 204
    assert len(sent) == 1


def test_checkout_session_expired_releases_reservation(client, db, monkeypatch):
    _use_webhook_secret(client)
    order, variant = pending_order(db)
    event = fake_event("evt_expired_1", "checkout.session.expired", order.id)
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    response = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=whatever"},
    )
    assert response.status_code == 204

    db.refresh(order)
    db.refresh(variant)
    assert order.status == OrderStatus.EXPIRED
    assert order.payment.status == PaymentStatus.FAILED
    assert variant.stock_reserved == 0
    assert variant.stock_on_hand == 4  # unchanged, only the reservation is released


def test_webhook_order_id_as_string_is_accepted(client, db, monkeypatch):
    """Real Stripe metadata values are always strings.

    app/api.py's stripe_webhook coerces the metadata `order_id` string to a
    `uuid.UUID` before calling `db.get(Order, ...)`, so a plain string (as
    Stripe actually sends) is handled correctly on SQLite (this test suite)
    as well as on Postgres in production.
    """
    _use_webhook_secret(client)
    order, variant = pending_order(db)
    event = {
        "id": "evt_string_order_id",
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"order_id": str(order.id)}}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    response = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=whatever"},
    )
    assert response.status_code == 204

    db.refresh(order)
    assert order.status == OrderStatus.PAID


def test_webhook_invalid_order_id_in_metadata_is_skipped_not_500(client, db, monkeypatch):
    """A malformed order_id in Stripe metadata should be logged and skipped,
    not crash the webhook handler. The event is still recorded as processed.
    """
    _use_webhook_secret(client)
    event = {
        "id": "evt_bad_order_id",
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"order_id": "not-a-uuid"}}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    response = client.post(
        "/api/v1/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=1,v1=whatever"},
    )
    assert response.status_code == 204
    assert db.get(ProcessedWebhook, event["id"]) is not None
