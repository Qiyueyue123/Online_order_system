import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, Session } from "../../api/client";
import { AdminOrders } from "./AdminOrders";
import { AdminProducts } from "./AdminProducts";
import { AdminAuditLog } from "./AdminAuditLog";
import { AdminPickupDays } from "./AdminPickupDays";

type Tab = "orders" | "products" | "pickup" | "audit";

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("orders");
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
  });

  if (session.isLoading) {
    return (
      <div className="page">
        <p role="status">Loading admin console…</p>
      </div>
    );
  }

  // Note: this check is UX only, to avoid flashing admin tooling at the
  // wrong users and to skip firing admin-only requests from the client.
  // The API is the real gate: every /admin/* endpoint re-checks the
  // session server-side and returns 401 (no session) or 403 (non-admin)
  // regardless of what this component renders.
  if (!session.data || session.data.user.role !== "admin") {
    return (
      <div className="page narrow">
        <h1>Not authorized</h1>
        <p>You need an administrator account to view this page.</p>
      </div>
    );
  }

  const csrfToken = session.data.csrf_token;

  return (
    <div className="page admin">
      <p className="eyebrow">ADMIN</p>
      <h1>Admin console</h1>
      <div className="admin-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "orders"}
          className={tab === "orders" ? "active" : ""}
          onClick={() => setTab("orders")}
        >
          Orders
        </button>
        <button
          role="tab"
          aria-selected={tab === "products"}
          className={tab === "products" ? "active" : ""}
          onClick={() => setTab("products")}
        >
          Products
        </button>
        <button
          role="tab"
          aria-selected={tab === "pickup"}
          className={tab === "pickup" ? "active" : ""}
          onClick={() => setTab("pickup")}
        >
          Pickup days
        </button>
        <button
          role="tab"
          aria-selected={tab === "audit"}
          className={tab === "audit" ? "active" : ""}
          onClick={() => setTab("audit")}
        >
          Audit log
        </button>
      </div>
      {tab === "orders" && <AdminOrders csrfToken={csrfToken} />}
      {tab === "products" && <AdminProducts csrfToken={csrfToken} />}
      {tab === "pickup" && <AdminPickupDays csrfToken={csrfToken} />}
      {tab === "audit" && <AdminAuditLog />}
    </div>
  );
}
