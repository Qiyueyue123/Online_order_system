import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, Cart, money } from "../api/client";

export function CartPage() {
  const cart = useQuery({ queryKey: ["cart"], queryFn: () => api<Cart>("/cart") });
  return (
    <div className="page narrow">
      <p className="eyebrow">YOUR SELECTION</p><h1>Shopping bag</h1>
      {cart.isLoading && <p role="status">Loading bag…</p>}
      {cart.data?.items.length === 0 && <div className="empty"><p>Your bag is empty.</p><Link className="button" to="/">Browse matcha</Link></div>}
      {cart.data?.items.map((item) => (
        <article className="cart-row" key={item.variant_id}>
          <div><h2>{item.product_name}</h2><p>{item.variant_name} · Qty {item.quantity}</p></div>
          <strong>{money(item.line_total_cents)}</strong>
        </article>
      ))}
      {!!cart.data?.items.length && (
        <>
          <div className="cart-total"><span>Subtotal</span><strong>{money(cart.data.subtotal_cents)}</strong></div>
          {cart.data.needs_pickup && (
            <div className="cart-total cart-total--pickup"><span>Pickup · dorm kitchen, Umeå</span><strong>{money(0)}</strong></div>
          )}
          {cart.data.needs_shipping && (
            <div className="cart-total cart-total--pickup"><span>Shipping</span><strong>Calculated at checkout</strong></div>
          )}
        </>
      )}
      {!!cart.data?.items.length && <Link className="button full" to="/checkout">Continue to checkout</Link>}
    </div>
  );
}
