from conftest import add_product

from app.config import get_settings
from app.models import Order, OrderItem, OrderStatus, Payment, PaymentStatus
from app.services.email import (
    ConsoleEmailBackend,
    EmailMessage,
    SmtpEmailBackend,
    _get_backend,
    _render_order_confirmation,
    send_order_confirmation,
)


def build_order(db):
    product = add_product(db)
    variant = product.variants[0]
    order = Order(
        display_number="M-EMAIL-1",
        email="guest@example.com",
        status=OrderStatus.PAID,
        subtotal_cents=6400,
        discount_cents=100,
        shipping_cents=600,
        total_cents=6900,
        shipping_name="Guest Person",
        shipping_line1="1 Tea Street",
        shipping_line2="Unit 02-03",
        shipping_city="Umea",
        shipping_postal_code="90325",
        shipping_country_code="SE",
        items=[
            OrderItem(
                variant_id=variant.id,
                product_name=product.name,
                variant_name=variant.name,
                sku=variant.sku,
                unit_price_cents=3200,
                quantity=2,
            )
        ],
        payment=Payment(status=PaymentStatus.SUCCEEDED, amount_cents=6900),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_backend_selection_defaults_to_console():
    settings = get_settings().model_copy(update={"email_backend": "console"})
    assert isinstance(_get_backend(settings), ConsoleEmailBackend)


def test_backend_selection_smtp():
    settings = get_settings().model_copy(
        update={"email_backend": "smtp", "smtp_host": "mailpit", "smtp_port": 1025}
    )
    backend = _get_backend(settings)
    assert isinstance(backend, SmtpEmailBackend)
    assert backend.host == "mailpit"
    assert backend.port == 1025


def test_render_order_confirmation_includes_line_items_and_money_formatting(db):
    order = build_order(db)
    body = _render_order_confirmation(order)

    assert order.display_number in body
    assert f"{product_line(order)}" in body
    assert "Subtotal: 64.00 SEK" in body
    assert "Shipping: 6.00 SEK" in body
    assert "Discount: 1.00 SEK" in body
    assert "Total: 69.00 SEK" in body
    assert "Guest Person" in body
    assert "Unit 02-03" in body


def test_render_order_confirmation_includes_contact_line(db):
    order = build_order(db)
    settings = get_settings().model_copy(
        update={"contact_telegram": "@notqiyue", "contact_whatsapp": "+65 9788 8146"}
    )
    body = _render_order_confirmation(order, settings)

    assert "Telegram @notqiyue" in body
    assert "WhatsApp +65 9788 8146" in body


def product_line(order):
    item = order.items[0]
    return f"{item.product_name} ({item.variant_name}) x{item.quantity} @ 32.00 SEK"


def test_send_order_confirmation_dispatches_through_backend(db, monkeypatch):
    order = build_order(db)
    sent = []

    class RecordingBackend:
        def send(self, message: EmailMessage) -> None:
            sent.append(message)

    monkeypatch.setattr("app.services.email._get_backend", lambda settings: RecordingBackend())

    send_order_confirmation(order, get_settings())

    assert len(sent) == 1
    assert sent[0].to == "guest@example.com"
    assert order.display_number in sent[0].subject
