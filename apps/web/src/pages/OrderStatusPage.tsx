import { useQuery } from "@tanstack/react-query";
import { useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, Order } from "../api/client";
import { OrderStatusView } from "../components/OrderStatusView";

export function OrderStatusPage() {
  const { id = "" } = useParams();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? sessionStorage.getItem("guestOrderToken");

  const order = useQuery({
    queryKey: ["order", id, token],
    queryFn: async () => {
      if (token) {
        try {
          return await api<Order>(`/orders/${id}?lookup_token=${encodeURIComponent(token)}`);
        } catch (error) {
          // Fall back to session auth (e.g. the token is stale but the viewer
          // is signed in as the order's owner) before giving up.
          if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
            return api<Order>(`/orders/${id}`);
          }
          throw error;
        }
      }
      return api<Order>(`/orders/${id}`);
    },
  });

  if (order.isLoading) {
    return (
      <div className="page narrow">
        <p role="status">Loading your order…</p>
      </div>
    );
  }
  if (order.isError || !order.data) {
    return (
      <div className="page narrow">
        <p role="alert">We couldn&rsquo;t find that order.</p>
      </div>
    );
  }
  return (
    <div className="page narrow">
      <OrderStatusView order={order.data} />
    </div>
  );
}
