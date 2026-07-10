import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
      id: "item-1",
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
      id: "item-2",
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

  it("hides the line and offers Undo when Remove is clicked, without deleting yet", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(cart), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<CartPage />);

    const row = (await screen.findByText("Ceremonial Matcha")).closest("article")!;
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));

    expect(await screen.findByText(/Removed Ceremonial Matcha/)).toBeInTheDocument();
    expect(screen.queryByText("Ceremonial Matcha")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
  });

  it("restores the line with no API call when Undo is clicked", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(cart), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<CartPage />);

    const row = (await screen.findByText("Ceremonial Matcha")).closest("article")!;
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));

    expect(await screen.findByText("Ceremonial Matcha")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
  });

  it("actually deletes the line once the undo window lapses", async () => {
    const cartAfterRemoval = { ...cart, items: [cart.items[1]], subtotal_cents: 4500 };
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return Promise.resolve(new Response(JSON.stringify(cartAfterRemoval), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify(cart), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    // Avoid vitest's fake timers here: they fight with testing-library's
    // internal polling. Instead, spy on the real setTimeout and invoke the
    // captured callback directly once we've confirmed the delay is correct.
    const setTimeoutSpy = vi.spyOn(window, "setTimeout");

    renderWithProviders(<CartPage />);

    const row = (await screen.findByText("Ceremonial Matcha")).closest("article")!;
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));

    const scheduled = setTimeoutSpy.mock.calls.find(([, delay]) => delay === 5000);
    expect(scheduled).toBeDefined();
    (scheduled![0] as () => void)();

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/cart/items/item-1",
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    setTimeoutSpy.mockRestore();
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
