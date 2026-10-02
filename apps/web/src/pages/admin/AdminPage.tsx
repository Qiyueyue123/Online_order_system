import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api, Session } from "../../api/client";
import { AdminOrders } from "./AdminOrders";
import { AdminProducts } from "./AdminProducts";
import { AdminAuditLog } from "./AdminAuditLog";
import { AdminPickupDays } from "./AdminPickupDays";
import { AdminNotices } from "./AdminNotices";

type Tab = "orders" | "products" | "pickup" | "notices" | "audit";

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("orders");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
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
  if (!session.data) {
    return <Navigate to="/signin" replace />;
  }
  if (session.data.user.role !== "admin") {
    return (
      <div className="page narrow">
        <h1>Nothing to see here</h1>
        <p>This page is just for the café team — there's nothing here for a customer account.</p>
        <Link className="button" to="/">Back to the menu</Link>
      </div>
    );
  }

  const csrfToken = session.data.csrf_token;

  return (
    <div className="page admin">
      <div className="admin-heading">
        <div><p className="eyebrow">ADMIN</p><h1>Admin console</h1></div>
        <button className="text-button" onClick={() => logout.mutate()}>Sign out</button>
      </div>
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
          aria-selected={tab === "notices"}
          className={tab === "notices" ? "active" : ""}
          onClick={() => setTab("notices")}
        >
          Noticeboard
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
      {tab === "notices" && <AdminNotices csrfToken={csrfToken} />}
      {tab === "audit" && <AdminAuditLog />}
    </div>
  );
}
