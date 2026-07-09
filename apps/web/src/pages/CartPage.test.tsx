import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Cart } from "../api/client";
import { CartPage } from "./CartPage";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const cart: Cart = {
  items: [
    {
      variant_id: "var-1",
      product_slug: "ceremonial-matcha",
      product_name: "Ceremonial Matcha",
      variant_name: "30g tin",
      sku: "SKU-1",
      quantity: 2,
      unit_price_cents: 3800,
      line_total_cents: 7600,
    },
    {
      variant_id: "var-2",
      product_slug: "matcha-whisk",
      product_name: "Bamboo Whisk",
      variant_name: "Standard",
      sku: "SKU-2",
      quantity: 1,
      unit_price_cents: 4500,
      line_total_cents: 4500,
    },
  ],
  subtotal_cents: 12100,
  currency: "SEK",
  needs_pickup: false,
  needs_shipping: true,
};

describe("CartPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows line items and the subtotal using money()", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(cart), { status: 200 })),
    );

    renderWithProviders(<CartPage />);

    expect(await screen.findByText("Ceremonial Matcha")).toBeInTheDocument();
    expect(screen.getByText("Bamboo Whisk")).toBeInTheDocument();
    expect(screen.getByText(/30g tin/)).toBeInTheDocument();
    expect(screen.getByText(/Qty 2/)).toBeInTheDocument();
    expect(screen.getByText(/76,00\s*kr/)).toBeInTheDocument();
    expect(screen.getByText(/45,00\s*kr/)).toBeInTheDocument();
    expect(screen.getByText(/121,00\s*kr/)).toBeInTheDocument();
  });

  it("shows an empty state when the bag has no items", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ items: [], subtotal_cents: 0, currency: "SEK" }), { status: 200 }),
      ),
    );

    renderWithProviders(<CartPage />);

    expect(await screen.findByText("Your bag is empty.")).toBeInTheDocument();
  });
});
