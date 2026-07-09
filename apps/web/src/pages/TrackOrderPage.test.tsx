import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Order } from "../api/client";
import { TrackOrderPage } from "./TrackOrderPage";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
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
  payment_method: "online",
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

function submitForm(container: HTMLElement) {
  const form = container.querySelector("form");
  if (!form) throw new Error("form not found");
  fireEvent.submit(form);
}

describe("TrackOrderPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("looks up an order by display number and email and renders its status", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(order), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderWithProviders(<TrackOrderPage />);
    fireEvent.change(screen.getByLabelText(/Order number/), { target: { value: "ORD-1001" } });
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    submitForm(container);

    expect(await screen.findByText("ORD-1001", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/oat whisk/)).toBeInTheDocument();
    expect(screen.getByText(/6 g sugar/)).toBeInTheDocument();

    const call = fetchMock.mock.calls[0];
    expect(String(call[0])).toContain("/orders/track?");
    expect(String(call[0])).toContain("display_number=ORD-1001");
    expect(String(call[0])).toContain("email=shopper%40example.com");
  });

  it("shows a friendly not-found message on a 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not found" }), { status: 404 })),
    );

    const { container } = renderWithProviders(<TrackOrderPage />);
    fireEvent.change(screen.getByLabelText(/Order number/), { target: { value: "ORD-9999" } });
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "nobody@example.com" } });
    submitForm(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("No order matches that number and email.");
  });

  it("shows a friendly rate-limit message on a 429", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Too many requests" }), { status: 429 })),
    );

    const { container } = renderWithProviders(<TrackOrderPage />);
    fireEvent.change(screen.getByLabelText(/Order number/), { target: { value: "ORD-1001" } });
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    submitForm(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });
});
