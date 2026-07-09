import { formatPickup, money, Order } from "../api/client";

// Live statuses form a straight-line progression; the rest are terminal
// end-states that replace the timeline with a single explanatory note.
const STEPS: { key: string; label: string }[] = [
  { key: "pending_payment", label: "Confirmed" },
  { key: "paid", label: "Paid" },
  { key: "fulfilled", label: "Fulfilled" },
];
const TERMINAL_NOTES: Record<string, string> = {
  cancelled: "This order was cancelled.",
  expired: "This order expired before payment was completed.",
  refunded: "This order was refunded.",
};

function formatItemOptions(options: Order["items"][number]["options"]): string | null {
  if (!options) return null;
  const whisk = (options as Record<string, unknown>).whisk;
  const sugar = (options as Record<string, unknown>).sugar_g;
  const parts: string[] = [];
  if (typeof whisk === "string") parts.push(`${whisk} whisk`);
  if (typeof sugar === "number") parts.push(`${sugar} g sugar`);
  return parts.length ? parts.join(" · ") : null;
}

export function OrderStatusView({ order }: { order: Order }) {
  const terminalNote = TERMINAL_NOTES[order.status];
  const activeIndex = STEPS.findIndex((step) => step.key === order.status);

  return (
    <div className="order-status-view">
      <div className="order-status-heading">
        <div>
          <p className="eyebrow">ORDER {order.display_number}</p>
          <h1>Tracking your order</h1>
        </div>
        <span className={`status status--${order.status}`}>{order.status.replace("_", " ")}</span>
      </div>

      {terminalNote ? (
        <p className="order-terminal-note" role="status">{terminalNote}</p>
      ) : (
        <ol className="order-timeline" aria-label="Order status timeline">
          {STEPS.map((step, index) => (
            <li key={step.key} className={index <= activeIndex ? "done" : ""}>{step.label}</li>
          ))}
        </ol>
      )}

      {order.payment_method === "pay_at_pickup" && order.status === "pending_payment" && (
        <p className="checkout-note">
          Pay at pickup — cash, Revolut, or Swish transfer, when you collect your order.
        </p>
      )}

      {order.pickup_at && <p className="pickup-time">Pickup {formatPickup(order.pickup_at)}</p>}

      <div className="order-items">
        {order.items.map((item, index) => {
          const options = formatItemOptions(item.options);
          return (
            <article className="cart-row" key={`${item.sku}-${index}`}>
              <div>
                <h2>{item.product_name}</h2>
                <p>{item.variant_name} · Qty {item.quantity}</p>
                {options && <p className="cart-options">{options}</p>}
              </div>
              <strong>{money(item.unit_price_cents * item.quantity)}</strong>
            </article>
          );
        })}
      </div>

      <div className="cart-total"><span>Total</span><strong>{money(order.total_cents)}</strong></div>
    </div>
  );
}
