import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Product } from "../api/client";
import { ProductPage } from "./ProductPage";

function renderWithProviders(ui: ReactElement, initialEntries: string[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/products/:slug" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const drink: Product = {
  id: "prod-drink",
  slug: "ajisai-latte",
  name: "Ajisai 2.0 Matcha Latte",
  description: "Whisked to order.",
  category: "Drinks",
  category_slug: "drinks",
  variants: [
    { id: "var-iced", sku: "SKU-D1", name: "Iced", weight_grams: 0, price_cents: 4000, available_stock: 10 },
  ],
  images: [],
};

const retail: Product = {
  id: "prod-retail",
  slug: "ceremonial-matcha",
  name: "Ceremonial Matcha",
  description: "A stone-ground matcha.",
  category: "Matcha tins",
  category_slug: "matcha",
  variants: [
    { id: "var-tin", sku: "SKU-1", name: "30g tin", weight_grams: 30, price_cents: 3800, available_stock: 10 },
  ],
  images: [],
};

function stubFetch(product: Product, cart: unknown = { items: [], subtotal_cents: 0, currency: "SEK" }) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/products/") && (!init || init.method === undefined)) {
      return Promise.resolve(new Response(JSON.stringify(product), { status: 200 }));
    }
    if (url.includes("/cart/items") && init?.method === "PUT") {
      return Promise.resolve(new Response(JSON.stringify(cart), { status: 200 }));
    }
    throw new Error(`Unexpected fetch to ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("ProductPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders drink option chips, defaults to the standard recipe, and hides the redundant single-variant picker", async () => {
    stubFetch(drink);
    renderWithProviders(<ProductPage />, ["/products/ajisai-latte"]);

    expect(await screen.findByText("Ajisai 2.0 Matcha Latte")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText(/Served iced/)).toBeInTheDocument();

    const matchaGroup = screen.getByRole("group", { name: "Matcha amount" });
    expect(within(matchaGroup).getByRole("button", { name: /4 g \(standard\)/ })).toHaveClass("active");
    const whiskGroup = screen.getByRole("group", { name: "Whisked with" });
    expect(within(whiskGroup).getByRole("button", { name: /Water \(standard\)/ })).toHaveClass("active");
    const milkGroup = screen.getByRole("group", { name: "Base milk" });
    expect(within(milkGroup).getByRole("button", { name: /Cow.s milk \(standard\)/ })).toHaveClass("active");
    const milkVolumeGroup = screen.getByRole("group", { name: "Milk amount" });
    expect(within(milkVolumeGroup).getByRole("button", { name: /130 ml \(standard\)/ })).toHaveClass("active");
    const sugarGroup = screen.getByRole("group", { name: "Sugar" });
    expect(within(sugarGroup).getByRole("button", { name: /4 g \(standard\)/ })).toHaveClass("active");

    expect(screen.getByRole("button", { name: /Add to bag — 40,00\s*kr/ })).toBeInTheDocument();
  });

  it("reflects the 6 g matcha upgrade surcharge in the add-to-bag price", async () => {
    stubFetch(drink);
    renderWithProviders(<ProductPage />, ["/products/ajisai-latte"]);

    await screen.findByText("Ajisai 2.0 Matcha Latte");
    const matchaGroup = screen.getByRole("group", { name: "Matcha amount" });
    fireEvent.click(within(matchaGroup).getByRole("button", { name: /6 g/ }));

    expect(screen.getByRole("button", { name: /Add to bag — 55,00\s*kr/ })).toBeInTheDocument();
  });

  it("sends the chosen drink options in the add-to-bag PUT body", async () => {
    const fetchMock = stubFetch(drink);
    renderWithProviders(<ProductPage />, ["/products/ajisai-latte"]);

    await screen.findByText("Ajisai 2.0 Matcha Latte");
    const whiskGroup = screen.getByRole("group", { name: "Whisked with" });
    fireEvent.click(within(whiskGroup).getByRole("button", { name: /Oat milk/ }));
    const milkGroup = screen.getByRole("group", { name: "Base milk" });
    fireEvent.click(within(milkGroup).getByRole("button", { name: "Oat milk" }));
    const milkVolumeGroup = screen.getByRole("group", { name: "Milk amount" });
    fireEvent.click(within(milkVolumeGroup).getByRole("button", { name: /160 ml/ }));
    const sugarGroup = screen.getByRole("group", { name: "Sugar" });
    fireEvent.click(within(sugarGroup).getByRole("button", { name: "6 g" }));
    fireEvent.click(screen.getByRole("button", { name: /Add to bag/ }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/cart/items",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(putCall![1]!.body as string);
    expect(body).toEqual({
      variant_id: "var-iced",
      quantity: 1,
      options: { matcha_g: 4, whisk: "oat", base_milk: "oat", milk_ml: 160, sugar_g: 6 },
    });
  });

  it("shows no options UI for a retail product and sends no options in the PUT body", async () => {
    const fetchMock = stubFetch(retail);
    renderWithProviders(<ProductPage />, ["/products/ceremonial-matcha"]);

    await screen.findByText("Ceremonial Matcha");
    expect(screen.queryByRole("group", { name: "Whisked with" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Sugar" })).not.toBeInTheDocument();
    expect(screen.getByText(/30g tin/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Add to bag/ }));
    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/cart/items",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(putCall![1]!.body as string);
    expect(body).toEqual({ variant_id: "var-tin", quantity: 1 });
  });
});
