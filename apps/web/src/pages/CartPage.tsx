import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, Cart, formatDrinkOptions, humanizeError, money } from "../api/client";

// How long "Removed. Undo" stays up before the line is actually deleted.
const UNDO_WINDOW_MS = 5000;

export function CartPage() {
  const queryClient = useQueryClient();
  const cart = useQuery({ queryKey: ["cart"], queryFn: () => api<Cart>("/cart") });
  const removeItem = useMutation({
    mutationFn: (itemId: string) => api<Cart>(`/cart/items/${itemId}`, { method: "DELETE" }),
    onSuccess: (updated) => queryClient.setQueryData(["cart"], updated),
  });
  // Items the shopper just clicked "Remove" on: hidden immediately, but not
  // actually deleted server-side until the undo window lapses.
  const [pendingRemoval, setPendingRemoval] = useState<Set<string>>(new Set());
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  function scheduleRemoval(itemId: string) {
    setPendingRemoval((current) => new Set(current).add(itemId));
    const timer = setTimeout(() => {
      timers.current.delete(itemId);
      removeItem.mutate(itemId);
    }, UNDO_WINDOW_MS);
    timers.current.set(itemId, timer);
  }

  function undoRemoval(itemId: string) {
    const timer = timers.current.get(itemId);
    if (timer) clearTimeout(timer);
    timers.current.delete(itemId);
    setPendingRemoval((current) => {
      const next = new Set(current);
      next.delete(itemId);
      return next;
    });
  }

  return (
    <div className="page narrow">
      <p className="eyebrow">YOUR SELECTION</p><h1>Shopping bag</h1>
      {cart.isLoading && <p role="status">Loading bag…</p>}
      {cart.data?.items.length === 0 && <div className="empty"><p>Your bag is empty.</p><Link className="button" to="/">Browse matcha</Link></div>}
      {removeItem.isError && <p role="alert">{humanizeError(removeItem.error)}</p>}
      {cart.data?.items.map((item) => {
        if (pendingRemoval.has(item.id)) {
          return (
            <article className="cart-row cart-row--removed" key={item.id}>
              <p>Removed {item.product_name}.</p>
              <button type="button" className="text-button" onClick={() => undoRemoval(item.id)}>
                Undo
              </button>
            </article>
          );
        }
        const options = formatDrinkOptions(item.options);
        return (
          <article className="cart-row" key={item.id}>
            <div>
              <h2>{item.product_name}</h2>
              <p>{item.variant_name} · Qty {item.quantity}</p>
              {options && <p className="cart-options">{options}</p>}
            </div>
            <div className="cart-row-end">
              <strong>{money(item.line_total_cents)}</strong>
              <button
                type="button"
                className="text-button"
                onClick={() => scheduleRemoval(item.id)}
              >
                Remove
              </button>
            </div>
          </article>
        );
      })}
      {(() => {
        const visible = cart.data?.items.filter((item) => !pendingRemoval.has(item.id)) ?? [];
        if (!visible.length) return null;
        const visibleSubtotal = visible.reduce((sum, item) => sum + item.line_total_cents, 0);
        return (
          <>
            <div className="cart-total"><span>Subtotal</span><strong>{money(visibleSubtotal)}</strong></div>
            {cart.data?.needs_pickup && (
              <div className="cart-total cart-total--pickup"><span>Pickup · dorm kitchen, Umeå</span><strong>{money(0)}</strong></div>
            )}
            {cart.data?.needs_shipping && (
              <div className="cart-total cart-total--pickup"><span>Shipping</span><strong>Calculated at checkout</strong></div>
            )}
            <Link className="button full" to="/checkout">Continue to checkout</Link>
          </>
        );
      })()}
    </div>
  );
}
