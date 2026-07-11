import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Cart, PickupDay, Product } from "../api/client";
import { OrderFlowPage } from "./OrderFlowPage";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/order"]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const drinkProduct: Product = {
  id: "prod-1",
  slug: "ajisai-latte",
  name: "Ajisai 2.0 Matcha Latte",
  description: "Whisked to order.",
  category: "Drinks",
  category_slug: "drinks",
  variants: [
    { id: "var-1", sku: "SKU-D1", name: "Iced", weight_grams: 0, price_cents: 4000, available_stock: 20 },
  ],
  images: [],
};

const emptyCart: Cart = {
  items: [],
  subtotal_cents: 0,
  currency: "SEK",
  needs_pickup: false,
  needs_shipping: false,
};

const pickupOnlyCart: Cart = {
  items: [
    {
      id: "item-1",
      variant_id: "var-1",
      product_slug: "ajisai-latte",
      product_name: "Ajisai 2.0 Matcha Latte",
      variant_name: "Iced",
      sku: "SKU-D1",
      quantity: 1,
      unit_price_cents: 4000,
      line_total_cents: 4000,
    },
  ],
  subtotal_cents: 4000,
  currency: "SEK",
  needs_pickup: true,
  needs_shipping: false,
};

const shippingCart: Cart = {
  items: [
    {
      id: "item-2",
      variant_id: "var-2",
      product_slug: "ceremonial-matcha",
      product_name: "Ceremonial Matcha",
      variant_name: "30g tin",
      sku: "SKU-1",
      quantity: 1,
      unit_price_cents: 3800,
      line_total_cents: 3800,
    },
  ],
  subtotal_cents: 3800,
  currency: "SEK",
  needs_pickup: false,
  needs_shipping: true,
};

const pickupDays: PickupDay[] = [
  {
    date: "2026-07-09",
    slots: [
      { time: "2026-07-09T16:00:00Z", remaining: 2 },
      { time: "2026-07-09T16:15:00Z", remaining: 5 },
    ],
  },
];

const signedInSession = {
  user: { id: "user-1", email: "account@example.com", name: "Ada", role: "customer", email_verified: true },
  csrf_token: "csrf-token",
};

function stubFetch({
  cart = emptyCart,
  products = [drinkProduct],
  days = pickupDays,
  signedIn = false,
  onlinePaymentsEnabled = true,
}: {
  cart?: Cart;
  products?: Product[];
  days?: PickupDay[];
  signedIn?: boolean;
  onlinePaymentsEnabled?: boolean;
} = {}) {
  let currentCart = cart;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/auth/session")) {
      return signedIn
        ? Promise.resolve(new Response(JSON.stringify(signedInSession), { status: 200 }))
        : Promise.resolve(new Response(JSON.stringify({ detail: "Authentication required" }), { status: 401 }));
    }
    if (url.includes("/storefront-config")) {
      return Promise.resolve(
        new Response(JSON.stringify({ online_payments_enabled: onlinePaymentsEnabled }), { status: 200 }),
      );
    }
    if (url.includes("/products?")) {
      return Promise.resolve(new Response(JSON.stringify({ items: products, total: products.length }), { status: 200 }));
    }
    if (url.includes("/pickup-days")) {
      return Promise.resolve(new Response(JSON.stringify(days), { status: 200 }));
    }
    if (url.includes("/cart/items") && init?.method === "PUT") {
      currentCart = pickupOnlyCart;
      return Promise.resolve(new Response(JSON.stringify(currentCart), { status: 200 }));
    }
    if (url.includes("/cart/items/") && init?.method === "DELETE") {
      currentCart = emptyCart;
      return Promise.resolve(new Response(JSON.stringify(currentCart), { status: 200 }));
    }
    if (url.endsWith("/cart")) {
      return Promise.resolve(new Response(JSON.stringify(currentCart), { status: 200 }));
    }
    if (url.includes("/checkout") && init?.method === "POST") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            order_id: "order-1",
            display_number: "M-0001",
            checkout_url: "https://stripe.example.com/session/abc",
            guest_lookup_token: null,
          }),
          { status: 201 },
        ),
      );
    }
    throw new Error(`Unexpected fetch to ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// The menu step's Continue CTA starts disabled until the cart query resolves
// (it's keyed off cart.isLoading/itemCount); wait for it to actually enable
// before clicking, rather than racing the cart fetch.
async function continueFromMenu() {
  const button = await screen.findByRole("button", { name: "Continue" });
  await vi.waitFor(() => expect(button).not.toBeDisabled());
  fireEvent.click(button);
}

describe("OrderFlowPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("renders the menu from the mocked product list", async () => {
    stubFetch();
    renderWithProviders(<OrderFlowPage />);

    expect(await screen.findByText("Ajisai 2.0 Matcha Latte")).toBeInTheDocument();
    expect(screen.getByText("What can we whisk for you?")).toBeInTheDocument();
  });

  it("selecting a product opens customise, and Add to order PUTs the options payload", async () => {
    const fetchMock = stubFetch();
    renderWithProviders(<OrderFlowPage />);

    fireEvent.click(await screen.findByText("Ajisai 2.0 Matcha Latte"));

    expect(await screen.findByRole("heading", { name: "Ajisai 2.0 Matcha Latte" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /6 g stronger/ }));
    fireEvent.click(screen.getByRole("button", { name: /Add to order/ }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/cart/items",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const call = fetchMock.mock.calls.find(
      ([input, init]) => String(input).includes("/cart/items") && init?.method === "PUT",
    );
    const body = JSON.parse(call![1]!.body as string);
    expect(body).toEqual({
      variant_id: "var-1",
      quantity: 1,
      options: { matcha_g: 6, whisk: "water", base_milk: "cow", milk_ml: 130, sugar_g: 4 },
    });

    // Returns to the menu step after a successful add.
    expect(await screen.findByText("What can we whisk for you?")).toBeInTheDocument();
  });

  it("hides the email input on the contact step when signed in", async () => {
    stubFetch({ cart: pickupOnlyCart, signedIn: true });
    renderWithProviders(<OrderFlowPage />);

    await continueFromMenu();

    expect(await screen.findByText(/Receipt goes to account@example.com/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^Email/)).not.toBeInTheDocument();
  });

  it("requires an email for guests before continuing past the contact step", async () => {
    stubFetch({ cart: pickupOnlyCart });
    renderWithProviders(<OrderFlowPage />);

    await continueFromMenu();

    await screen.findByLabelText(/Email/);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid email to continue.");
    // Still on the contact step, not advanced to pickup.
    expect(screen.queryByRole("group", { name: "Pickup day" })).not.toBeInTheDocument();
  });

  it("disables the pickup step CTA until a slot is picked", async () => {
    stubFetch({ cart: pickupOnlyCart });
    renderWithProviders(<OrderFlowPage />);

    await continueFromMenu();
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
    const continueButton = screen.getByRole("button", { name: "Continue" });
    expect(continueButton).toBeDisabled();

    fireEvent.click(within(slotGroup).getAllByRole("button")[0]);
    expect(continueButton).not.toBeDisabled();
  });

  it("submits pickup_at and payment_method to /checkout", async () => {
    const fetchMock = stubFetch({ cart: pickupOnlyCart });
    renderWithProviders(<OrderFlowPage />);

    await continueFromMenu();
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
    fireEvent.click(within(slotGroup).getAllByRole("button")[1]);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    fireEvent.click(await screen.findByRole("button", { name: /Continue to payment|Confirm order/ }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/checkout", expect.objectContaining({ method: "POST" })),
    );
    const call = fetchMock.mock.calls.find(
      ([input, init]) => String(input).includes("/checkout") && init?.method === "POST",
    );
    const body = JSON.parse(call![1]!.body as string);
    expect(body.pickup_at).toBe("2026-07-09T16:15:00Z");
    expect(body.payment_method).toBe("online");
    expect(body.email).toBe("shopper@example.com");
  });

  it("shows a full-checkout notice instead of payment options when the cart needs shipping", async () => {
    stubFetch({ cart: shippingCart });
    renderWithProviders(<OrderFlowPage />);

    await continueFromMenu();
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    // Shipping-only cart has no pickup step, so Continue goes straight to payment.
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText(/use the/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "full checkout" })).toHaveAttribute("href", "/checkout");
    expect(screen.queryByRole("radiogroup", { name: "Payment method" })).not.toBeInTheDocument();
  });

  it("hides the payment radio and submits pay_at_pickup when online payments are disabled", async () => {
    const fetchMock = stubFetch({ cart: pickupOnlyCart, onlinePaymentsEnabled: false });
    renderWithProviders(<OrderFlowPage />);

    await continueFromMenu();
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
    fireEvent.click(within(slotGroup).getAllByRole("button")[1]);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText(/Pay when you collect/)).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Payment method" })).not.toBeInTheDocument();
    const submitButton = await screen.findByRole("button", { name: "Confirm order — pay at pickup" });
    fireEvent.click(submitButton);

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/checkout", expect.objectContaining({ method: "POST" })),
    );
    const call = fetchMock.mock.calls.find(
      ([input, init]) => String(input).includes("/checkout") && init?.method === "POST",
    );
    const body = JSON.parse(call![1]!.body as string);
    expect(body.payment_method).toBe("pay_at_pickup");
  });
});
