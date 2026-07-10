import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProductPage } from "../api/client";
import { CatalogPage } from "./CatalogPage";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const productPage: ProductPage = {
  items: [
    {
      id: "prod-1",
      slug: "ceremonial-matcha",
      name: "Ceremonial Matcha",
      description: "A stone-ground matcha.",
      category: "matcha",
      category_slug: "matcha",
      variants: [
        {
          id: "var-1",
          sku: "SKU-1",
          name: "30g tin",
          weight_grams: 30,
          price_cents: 3800,
          available_stock: 10,
        },
      ],
      images: [],
    },
    {
      id: "prod-2",
      slug: "matcha-whisk",
      name: "Bamboo Whisk",
      description: "A hand-carved whisk.",
      category: "tools",
      category_slug: "tools",
      variants: [
        {
          id: "var-2",
          sku: "SKU-2",
          name: "Standard",
          weight_grams: 50,
          price_cents: 4500,
          available_stock: 5,
        },
      ],
      images: [],
    },
  ],
  page: 1,
  page_size: 20,
  total: 2,
};

describe("CatalogPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders products returned by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/notices")) {
          return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
        }
        return Promise.resolve(new Response(JSON.stringify(productPage), { status: 200 }));
      }),
    );

    renderWithProviders(<CatalogPage />);

    expect(await screen.findByText("Ceremonial Matcha")).toBeInTheDocument();
    expect(screen.getByText("Bamboo Whisk")).toBeInTheDocument();
    expect(screen.getByText(/38,00\s*kr/)).toBeInTheDocument();
    expect(screen.getByText(/45,00\s*kr/)).toBeInTheDocument();

    await waitFor(() => expect(screen.queryByText(/Preparing the collection/)).not.toBeInTheDocument());
  });

  it("shows active notices above the menu", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/notices")) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  id: "notice-1",
                  title: "Closed this weekend",
                  body: "We're away at a matcha festival — back Monday.",
                  created_at: new Date().toISOString(),
                },
              ]),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify(productPage), { status: 200 }));
      }),
    );

    renderWithProviders(<CatalogPage />);

    expect(await screen.findByText("Closed this weekend")).toBeInTheDocument();
    expect(
      screen.getByText("We're away at a matcha festival — back Monday."),
    ).toBeInTheDocument();
  });

  it("renders nothing extra when the notices request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/notices")) {
          return Promise.resolve(new Response(JSON.stringify({ detail: "nope" }), { status: 500 }));
        }
        return Promise.resolve(new Response(JSON.stringify(productPage), { status: 200 }));
      }),
    );

    renderWithProviders(<CatalogPage />);

    expect(await screen.findByText("Ceremonial Matcha")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Shop notices" })).not.toBeInTheDocument();
  });
});
