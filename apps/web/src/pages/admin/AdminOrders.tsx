import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminOrder, AdminOrderPage, api, money } from "../../api/client";

const STATUS_OPTIONS = ["all", "pending_payment", "paid", "fulfilled", "refunded", "cancelled"];

// Only these transitions are offered in the UI; the API rejects any other
// transition, but keeping the button set narrow avoids surfacing actions
// that would just bounce back as a 409.
const TRANSITIONS: Record<string, { status: string; label: string }[]> = {
  pending_payment: [{ status: "cancelled", label: "Cancel" }],
  paid: [
    { status: "fulfilled", label: "Mark fulfilled" },
    { status: "refunded", label: "Refund" },
  ],
};

export function AdminOrders({ csrfToken }: { csrfToken: string }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("all");
  const orders = useQuery({
    queryKey: ["admin", "orders", status],
    queryFn: () =>
      api<AdminOrderPage>(
        `/admin/orders?page=1&page_size=50${status === "all" ? "" : `&status=${status}`}`,
      ),
  });
  const updateStatus = useMutation({
    mutationFn: ({ id, next }: { id: string; next: string }) =>
      api<AdminOrder>(`/admin/orders/${id}`, {
        method: "PATCH",
        headers: { "X-CSRF-Token": csrfToken },
        body: JSON.stringify({ status: next }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "orders"] }),
  });

  return (
    <div className="admin-orders">
      <label>
        Filter by status
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          {STATUS_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option === "all" ? "All statuses" : option.replace("_", " ")}
            </option>
          ))}
        </select>
      </label>
      {orders.isLoading && <p role="status">Loading orders…</p>}
      {updateStatus.isError && <p role="alert">{updateStatus.error.message}</p>}
      <table>
        <thead>
          <tr>
            <th>Order</th>
            <th>Email</th>
            <th>Status</th>
            <th>Total</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {orders.data?.items.map((order) => (
            <tr key={order.id}>
              <td>{order.display_number}</td>
              <td>{order.email}</td>
              <td>
                <span className={`status status--${order.status}`}>{order.status.replace("_", " ")}</span>
              </td>
              <td>{money(order.total_cents)}</td>
              <td>{new Date(order.created_at).toLocaleString()}</td>
              <td>
                {(TRANSITIONS[order.status] ?? []).map((transition) => (
                  <button
                    key={transition.status}
                    disabled={updateStatus.isPending}
                    onClick={() => updateStatus.mutate({ id: order.id, next: transition.status })}
                  >
                    {transition.label}
                  </button>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {orders.data?.items.length === 0 && <p>No orders match this filter.</p>}
    </div>
  );
}
