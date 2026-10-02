import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProductPage } from "../api/client";
import { StorePage } from "./StorePage";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const retailPage: ProductPage = {
  items: [
    {
      id: "prod-1",
      slug: "ajisai-jar",
      name: "Ajisai Jar",
      description: "Take-home tin.",
      category: "matcha",
      category_slug: "matcha",
      variants: [{ id: "var-1", sku: "SKU-1", name: "100g", weight_grams: 100, price_cents: 12000, available_stock: 5 }],
      images: [],
    },
    {
      id: "prod-2",
      slug: "bamboo-whisk",
      name: "Bamboo Whisk",
      description: "A hand-carved whisk.",
      category: "matcha",
      category_slug: "matcha",
      variants: [{ id: "var-2", sku: "SKU-2", name: "Standard", weight_grams: 50, price_cents: 4500, available_stock: 5 }],
      images: [],
    },
  ],
  page: 1,
  page_size: 20,
  total: 2,
};

describe("StorePage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders retail products from the API alongside non-purchasable placeholder cards", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(retailPage), { status: 200 })));

    renderWithProviders(<StorePage />);

    expect(await screen.findByText("Ajisai Jar")).toBeInTheDocument();
    expect(screen.getByText("Bamboo Whisk")).toBeInTheDocument();

    // Placeholder cards are clearly non-purchasable: no link to a product page,
    // labelled "Coming soon" instead of a price.
    expect(screen.getByText("Seasonal tins")).toBeInTheDocument();
    expect(screen.getByText("Brewing tools")).toBeInTheDocument();
    const comingSoonBadges = screen.getAllByText("Coming soon");
    expect(comingSoonBadges.length).toBeGreaterThan(0);
  });
});
