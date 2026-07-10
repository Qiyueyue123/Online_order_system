import json
import logging
import smtplib
from dataclasses import dataclass
from datetime import UTC
from email.message import EmailMessage as MimeEmailMessage

from ..config import Settings, get_settings
from ..models import Order
from .pickup import cafe_tz

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    to: str
    subject: str
    text_body: str


class ConsoleEmailBackend:
    """Logs the full message via the app logger instead of sending it.

    Default backend; visible in `docker compose logs api` for local/demo use.
    """

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email to=%s subject=%r\n%s", message.to, message.subject, message.text_body
        )


class SmtpEmailBackend:
    """Plain SMTP, no TLS — matches a local Mailpit container, not a production relay."""

    def __init__(self, host: str, port: int, sender: str):
        self.host = host
        self.port = port
        self.sender = sender

    def send(self, message: EmailMessage) -> None:
        mime_message = MimeEmailMessage()
        mime_message["From"] = self.sender
        mime_message["To"] = message.to
        mime_message["Subject"] = message.subject
        mime_message.set_content(message.text_body)
        with smtplib.SMTP(self.host, self.port) as smtp:
            smtp.send_message(mime_message)


def _get_backend(settings: Settings):
    if settings.email_backend == "smtp":
        return SmtpEmailBackend(settings.smtp_host, settings.smtp_port, settings.email_from)
    return ConsoleEmailBackend()


def _format_money(cents: int) -> str:
    return f"{cents / 100:.2f}"


def _format_options_suffix(raw_options: str | None) -> str:
    if not raw_options:
        return ""
    options = json.loads(raw_options)
    matcha_g = options.get("matcha_g", 4)
    whisk = options.get("whisk", "water")
    base_milk = options.get("base_milk", "cow")
    milk_ml = options.get("milk_ml", 130)
    sugar_g = options.get("sugar_g", 4)
    return (
        f" — {matcha_g} g matcha, {whisk} whisk, {base_milk} milk {milk_ml} ml, "
        f"{sugar_g} g sugar"
    )


def _render_order_confirmation(order: Order, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    lines = [
        f"Order {order.display_number}",
        "",
        "Items:",
    ]
    for item in order.items:
        lines.append(
            f"  {item.product_name} ({item.variant_name}) x{item.quantity} "
            f"@ {_format_money(item.unit_price_cents)} {order.currency}"
            f"{_format_options_suffix(item.options)}"
        )
    lines += [
        "",
        f"Subtotal: {_format_money(order.subtotal_cents)} {order.currency}",
        f"Shipping: {_format_money(order.shipping_cents)} {order.currency}",
        f"Discount: {_format_money(order.discount_cents)} {order.currency}",
        f"Total: {_format_money(order.total_cents)} {order.currency}",
    ]
    if order.payment_method == "pay_at_pickup":
        money = f"{_format_money(order.total_cents)} {order.currency}"
        payment_line = f"Pay {money} at pickup — "
        if settings.pickup_payment_note:
            payment_line += f"cash, or transfer via Revolut/Swish to {settings.pickup_payment_note}"
        else:
            payment_line += "cash at pickup"
        lines += ["", payment_line]
    if order.pickup_at is not None:
        # Stored as UTC (naive when read back from SQLite); the receipt must show
        # café wall-clock time, since pickup happens at a physical location.
        pickup_at = order.pickup_at
        if pickup_at.tzinfo is None:
            pickup_at = pickup_at.replace(tzinfo=UTC)
        local = pickup_at.astimezone(cafe_tz())
        lines += [
            "",
            f"Pickup: {local:%a %d %b %Y, %H:%M} at the dorm kitchen, Umeå",
        ]
    if order.shipping_line1:
        lines += [
            "",
            "Shipping to:",
            f"  {order.shipping_name}",
            f"  {order.shipping_line1}",
        ]
        if order.shipping_line2:
            lines.append(f"  {order.shipping_line2}")
        lines += [
            f"  {order.shipping_city} {order.shipping_postal_code}",
            f"  {order.shipping_country_code}",
        ]
    lines += [
        "",
        "This is a demonstration store; no real payment or shipment has taken place.",
        "",
        f"Questions or payment issues? Telegram {settings.contact_telegram} or "
        f"WhatsApp {settings.contact_whatsapp}.",
    ]
    return "\n".join(lines)


def send_order_confirmation(order: Order, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    message = EmailMessage(
        to=order.email,
        subject=f"Order confirmation - {order.display_number}",
        text_body=_render_order_confirmation(order, settings),
    )
    _get_backend(settings).send(message)
