import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, formatPickup, money, Order, Session } from "../api/client";

export function AccountPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
  });
  const orders = useQuery({
    queryKey: ["orders"],
    queryFn: () => api<Order[]>("/orders"),
    enabled: !!session.data,
  });
  const logout = useMutation({
    mutationFn: () =>
      api<void>("/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": session.data?.csrf_token ?? "" },
      }),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["session"] });
      queryClient.invalidateQueries({ queryKey: ["cart"] });
      navigate("/");
    },
  });
  if (session.isLoading) return <div className="page"><p role="status">Loading account…</p></div>;
  if (!session.data) return <div className="page narrow"><h1>Sign in required</h1><Link className="button" to="/signin">Sign in</Link></div>;
  return (
    <div className="page narrow account">
      <div className="account-heading">
        <div><p className="eyebrow">ACCOUNT</p><h1>Hello, {session.data.user.name}.</h1></div>
        <button className="text-button" onClick={() => logout.mutate()}>Sign out</button>
      </div>
      <h2>Your orders</h2>
      {orders.isLoading && <p role="status">Loading orders…</p>}
      {orders.data?.length === 0 && <p>You have no account orders yet.</p>}
      {orders.data?.map((order) => (
        <article className="order-card" key={order.id}>
          <div>
            <strong>{order.display_number}</strong>
            <p>{order.items.map((item) => `${item.product_name} × ${item.quantity}`).join(", ")}</p>
            {order.pickup_at && <p className="pickup-time">Pickup {formatPickup(order.pickup_at)}</p>}
          </div>
          <div><span className={`status status--${order.status}`}>{order.status.replace("_", " ")}</span><strong>{money(order.total_cents)}</strong></div>
        </article>
      ))}
    </div>
  );
}
