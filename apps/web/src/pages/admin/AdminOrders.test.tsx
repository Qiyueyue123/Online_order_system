import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AdminOrderPage } from "../../api/client";
import { AdminOrders } from "./AdminOrders";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const ordersPage: AdminOrderPage = {
  items: [
    {
      id: "order-1",
      display_number: "MO-1001",
      status: "paid",
      email: "shopper@example.com",
      subtotal_cents: 3800,
      discount_cents: 0,
      shipping_cents: 500,
      total_cents: 4300,
      currency: "SEK",
      pickup_at: null,
      payment_method: "online",
      items: [],
      created_at: "2026-01-01T00:00:00Z",
      user_id: null,
    },
  ],
  page: 1,
  page_size: 50,
  total: 1,
};

describe("AdminOrders", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders orders and shows only valid status transitions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(ordersPage), { status: 200 })),
    );

    renderWithProviders(<AdminOrders csrfToken="csrf-token-1" />);

    expect(await screen.findByText("MO-1001")).toBeInTheDocument();
    expect(screen.getByText("shopper@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark fulfilled" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refund" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("calls PATCH with the CSRF header when a valid transition button is clicked", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(
          new Response(JSON.stringify({ ...ordersPage.items[0], status: "fulfilled" }), { status: 200 }),
        );
      }
      if (url.includes("/admin/orders")) {
        return Promise.resolve(new Response(JSON.stringify(ordersPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminOrders csrfToken="csrf-token-1" />);

    const button = await screen.findByRole("button", { name: "Mark fulfilled" });
    fireEvent.click(button);

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/orders/order-1",
        expect.objectContaining({
          method: "PATCH",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(patchCall![1]!.body as string)).toEqual({ status: "fulfilled" });
  });

  it("shows the API error detail when a transition fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Order is not in a fulfillable state." }), { status: 409 }),
        );
      }
      if (url.includes("/admin/orders")) {
        return Promise.resolve(new Response(JSON.stringify(ordersPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminOrders csrfToken="csrf-token-1" />);

    const button = await screen.findByRole("button", { name: "Mark fulfilled" });
    fireEvent.click(button);

    expect(await screen.findByRole("alert")).toHaveTextContent("Order is not in a fulfillable state.");
  });
});
