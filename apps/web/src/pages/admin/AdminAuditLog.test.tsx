import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuditLogPage } from "../../api/client";
import { AdminAuditLog } from "./AdminAuditLog";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const auditLogPage: AuditLogPage = {
  items: [
    {
      id: "log-2",
      actor_user_id: "admin-1",
      action: "order.status_changed",
      entity_type: "order",
      entity_id: "order-1",
      detail: { from: "paid", to: "fulfilled" },
      created_at: "2026-01-02T00:00:00Z",
    },
    {
      id: "log-1",
      actor_user_id: "admin-1",
      action: "variant.updated",
      entity_type: "variant",
      entity_id: "variant-1",
      detail: null,
      created_at: "2026-01-01T00:00:00Z",
    },
  ],
  page: 1,
  page_size: 20,
  total: 2,
};

describe("AdminAuditLog", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders audit log rows newest-first as returned by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(auditLogPage), { status: 200 })),
    );

    renderWithProviders(<AdminAuditLog />);

    expect(await screen.findByText("order.status_changed")).toBeInTheDocument();
    expect(screen.getByText("variant.updated")).toBeInTheDocument();
    const rows = screen.getAllByRole("row");
    // header row + 2 data rows, newest (order.status_changed) first
    expect(rows[1]).toHaveTextContent("order.status_changed");
    expect(rows[2]).toHaveTextContent("variant.updated");
    expect(screen.getByText("Page 1 of 1")).toBeInTheDocument();
  });
});
