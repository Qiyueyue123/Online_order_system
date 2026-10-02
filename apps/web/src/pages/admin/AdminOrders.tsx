import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminOrder, AdminOrderPage, api, formatPickup, humanizeError, money } from "../../api/client";

const STATUS_OPTIONS = [
  "all",
  "pending_payment",
  "confirmed",
  "paid",
  "fulfilled",
  "refunded",
  "cancelled",
];

// Only these transitions are offered in the UI; the API rejects any other
// transition, but keeping the button set narrow avoids surfacing actions
// that would just bounce back as a 409. `confirm` gates a transition behind
// a window.confirm() prompt -- cancelling or refunding a real customer's
// order is hard to undo, so a misclick shouldn't be able to fire it outright.
const TRANSITIONS: Record<string, { status: string; label: string; confirm?: boolean }[]> = {
  pending_payment: [{ status: "cancelled", label: "Cancel", confirm: true }],
  paid: [
    { status: "fulfilled", label: "Mark fulfilled" },
    { status: "refunded", label: "Refund", confirm: true },
  ],
  confirmed: [
    { status: "fulfilled", label: "Mark fulfilled" },
    { status: "cancelled", label: "Cancel", confirm: true },
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

  function requestTransition(order: AdminOrder, transition: { status: string; label: string; confirm?: boolean }) {
    if (transition.confirm) {
      const verb = transition.label.toLowerCase();
      const proceed = window.confirm(
        `${transition.label} order ${order.display_number} for ${money(order.total_cents)}? ` +
          `This can't be undone once you ${verb} it.`,
      );
      if (!proceed) return;
    }
    updateStatus.mutate({ id: order.id, next: transition.status });
  }

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
      {updateStatus.isError && <p role="alert">{humanizeError(updateStatus.error)}</p>}
      <table>
        <thead>
          <tr>
            <th>Order</th>
            <th>Email</th>
            <th>Status</th>
            <th>Total</th>
            <th>Pickup</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {orders.data?.items.map((order) => (
            <tr key={order.id}>
              <td>{order.display_number}</td>
              <td>
                {order.email}
                {order.contact_handle && (
                  <div className="admin-order-contact">Backup contact: {order.contact_handle}</div>
                )}
              </td>
              <td>
                <span className={`status status--${order.status}`}>{order.status.replace("_", " ")}</span>
              </td>
              <td>{money(order.total_cents)}</td>
              <td>{order.pickup_at ? formatPickup(order.pickup_at) : "—"}</td>
              <td>{new Date(order.created_at).toLocaleString()}</td>
              <td>
                {(TRANSITIONS[order.status] ?? []).map((transition) => (
                  <button
                    key={transition.status}
                    disabled={updateStatus.isPending}
                    onClick={() => requestTransition(order, transition)}
                  >
                    {transition.label}
                  </button>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {orders.data?.items.length === 0 && (
        <p>
          No orders here yet — try a different status, or check back once new orders come in.
          {status !== "all" && (
            <>
              {" "}
              <button type="button" className="text-button" onClick={() => setStatus("all")}>
                Show all statuses
              </button>
            </>
          )}
        </p>
      )}
    </div>
  );
}
