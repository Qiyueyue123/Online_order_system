import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Order } from "../api/client";
import { OrderStatusPage } from "./OrderStatusPage";

function renderWithProviders(ui: ReactElement, initialEntries: string[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/orders/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const order: Order = {
  id: "order-1",
  display_number: "ORD-1001",
  status: "paid",
  email: "shopper@example.com",
  subtotal_cents: 4000,
  discount_cents: 0,
  shipping_cents: 0,
  total_cents: 4000,
  currency: "SEK",
  pickup_at: "2026-07-09T16:15:00Z",
  payment_method: "pay_at_pickup",
  items: [
    {
      product_name: "Ajisai 2.0 Matcha Latte",
      variant_name: "Iced",
      sku: "SKU-D1",
      unit_price_cents: 4000,
      quantity: 1,
      options: { whisk: "oat", sugar_g: 6 },
    },
  ],
};

describe("OrderStatusPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it("looks up the order with the token query param and renders the status timeline with item options", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("lookup_token=guest-token-123")) {
        return Promise.resolve(new Response(JSON.stringify(order), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<OrderStatusPage />, ["/orders/order-1?token=guest-token-123"]);

    expect(await screen.findByText(/ORD-1001/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Order status timeline" })).toBeInTheDocument();
    expect(screen.getByText(/oat whisk/)).toBeInTheDocument();
    expect(screen.getByText(/6 g sugar/)).toBeInTheDocument();
  });

  it("falls back to sessionStorage's guest token when no query param is present", async () => {
    sessionStorage.setItem("guestOrderToken", "stored-token-456");
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("lookup_token=stored-token-456")) {
        return Promise.resolve(new Response(JSON.stringify(order), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<OrderStatusPage />, ["/orders/order-1"]);

    expect(await screen.findByText(/ORD-1001/)).toBeInTheDocument();
  });

  it("shows a friendly not-found message when the order can't be loaded", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not found" }), { status: 404 })),
    );

    renderWithProviders(<OrderStatusPage />, ["/orders/missing"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("find that order");
  });
});
