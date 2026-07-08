import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeEmailMessage

from ..config import Settings, get_settings
from ..models import Order

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


def _render_order_confirmation(order: Order) -> str:
    lines = [
        f"Order {order.display_number}",
        "",
        "Items:",
    ]
    for item in order.items:
        lines.append(
            f"  {item.product_name} ({item.variant_name}) x{item.quantity} "
            f"@ {_format_money(item.unit_price_cents)} SGD"
        )
    lines += [
        "",
        f"Subtotal: {_format_money(order.subtotal_cents)} SGD",
        f"Shipping: {_format_money(order.shipping_cents)} SGD",
        f"Discount: {_format_money(order.discount_cents)} SGD",
        f"Total: {_format_money(order.total_cents)} SGD",
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
        "",
        "This is a demonstration store; no real payment or shipment has taken place.",
    ]
    return "\n".join(lines)


def send_order_confirmation(order: Order, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    message = EmailMessage(
        to=order.email,
        subject=f"Order confirmation - {order.display_number}",
        text_body=_render_order_confirmation(order),
    )
    _get_backend(settings).send(message)
