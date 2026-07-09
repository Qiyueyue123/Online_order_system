import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProductPage } from "../../api/client";
import { AdminProducts } from "./AdminProducts";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const productsPage: ProductPage = {
  items: [
    {
      id: "product-1",
      slug: "ceremonial-matcha",
      name: "Ceremonial Matcha",
      description: "Stone-ground matcha.",
      category: "tea",
      category_slug: "tea",
      images: [],
      variants: [
        {
          id: "variant-1",
          sku: "SKU-1",
          name: "30g tin",
          weight_grams: 30,
          price_cents: 3800,
          available_stock: 12,
        },
      ],
    },
  ],
  page: 1,
  page_size: 100,
  total: 1,
};

describe("AdminProducts", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders products with their variants", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(productsPage), { status: 200 })),
    );

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    expect(await screen.findByText("Ceremonial Matcha")).toBeInTheDocument();
    expect(screen.getByText("30g tin")).toBeInTheDocument();
    expect(screen.getByLabelText("30g tin price")).toHaveValue(38);
    expect(screen.getByLabelText("30g tin stock")).toHaveValue(12);
  });

  it("sends the edited stock (and unchanged price) when a variant is saved", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.includes("/products")) {
        return Promise.resolve(new Response(JSON.stringify(productsPage), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);

    const stockInput = await screen.findByLabelText("30g tin stock");
    fireEvent.change(stockInput, { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/variants/variant-1",
        expect.objectContaining({
          method: "PATCH",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    const body = JSON.parse(patchCall![1]!.body as string);
    expect(body.stock_on_hand).toBe(25);
    expect(body.price_cents).toBe(3800);
    expect(typeof body.reason).toBe("string");
    expect(body.reason.length).toBeGreaterThan(0);
  });

  it("shows a validation error and does not submit when the new-product form is incomplete", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(productsPage), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminProducts csrfToken="csrf-token-1" />);
    await screen.findByText("Ceremonial Matcha");

    fireEvent.click(screen.getByRole("button", { name: "Create product" }));

    expect(await screen.findByText("Name is required.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
