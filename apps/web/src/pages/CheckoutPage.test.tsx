import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Cart, PickupDay } from "../api/client";
import { CheckoutPage } from "./CheckoutPage";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

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
      unit_price_cents: 5500,
      line_total_cents: 5500,
    },
  ],
  subtotal_cents: 5500,
  currency: "SEK",
  needs_pickup: true,
  needs_shipping: false,
};

const retailOnlyCart: Cart = {
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

const mixedCart: Cart = {
  items: [...pickupOnlyCart.items, ...retailOnlyCart.items],
  subtotal_cents: pickupOnlyCart.subtotal_cents + retailOnlyCart.subtotal_cents,
  currency: "SEK",
  needs_pickup: true,
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
  {
    date: "2026-07-10",
    slots: [{ time: "2026-07-10T16:00:00Z", remaining: 1 }],
  },
];

const signedInSession = {
  user: { id: "user-1", email: "account@example.com", name: "Ada", role: "customer", email_verified: true },
  csrf_token: "csrf-token",
};

function stubFetch(
  cart: Cart,
  days: PickupDay[] = pickupDays,
  options: { signedIn?: boolean; onlinePaymentsEnabled?: boolean } = {},
) {
  const onlinePaymentsEnabled = options.onlinePaymentsEnabled ?? true;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/auth/session")) {
      return options.signedIn
        ? Promise.resolve(new Response(JSON.stringify(signedInSession), { status: 200 }))
        : Promise.resolve(new Response(JSON.stringify({ detail: "Authentication required" }), { status: 401 }));
    }
    if (url.includes("/storefront-config")) {
      return Promise.resolve(
        new Response(JSON.stringify({ online_payments_enabled: onlinePaymentsEnabled }), { status: 200 }),
      );
    }
    if (url.includes("/pickup-days")) {
      return Promise.resolve(new Response(JSON.stringify(days), { status: 200 }));
    }
    if (url.includes("/cart")) {
      return Promise.resolve(new Response(JSON.stringify(cart), { status: 200 }));
    }
    if (url.includes("/checkout") && init?.method === "POST") {
      return Promise.resolve(
        new Response(
          JSON.stringify({ checkout_url: "https://stripe.example.com/session/abc", guest_lookup_token: null }),
          { status: 201 },
        ),
      );
    }
    throw new Error(`Unexpected fetch to ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function submitForm(container: HTMLElement) {
  const form = container.querySelector("form");
  if (!form) throw new Error("form not found");
  fireEvent.submit(form);
}

describe("CheckoutPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("renders a pickup slot picker (not an address form) for a pickup-only cart", async () => {
    stubFetch(pickupOnlyCart);

    renderWithProviders(<CheckoutPage />);

    expect(await screen.findByRole("group", { name: "Pickup day" })).toBeInTheDocument();
    const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
    expect(slotGroup).toBeInTheDocument();
    // Slots render in café time (Europe/Stockholm), not the viewer's timezone:
    // the 2026-07-09T16:00:00Z fixture is 18:00 in Umeå (CEST), and the test
    // runner's TZ is pinned to UTC, so "16:00" here would mean viewer-local
    // rendering leaked back in.
    expect(within(slotGroup).getByRole("button", { name: /18:00/ })).toBeInTheDocument();
    expect(within(slotGroup).queryByRole("button", { name: /16:00/ })).not.toBeInTheDocument();
    // Day chips are date-only labels formatted in UTC; 2026-07-09 is a Thursday.
    const dayGroup = screen.getByRole("group", { name: "Pickup day" });
    expect(within(dayGroup).getByRole("button", { name: /Thu/ })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Recipient name/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^City/)).not.toBeInTheDocument();
  });

  it("renders the address form (not a slot picker) for a retail-only cart", async () => {
    stubFetch(retailOnlyCart);

    renderWithProviders(<CheckoutPage />);

    expect(await screen.findByLabelText(/Recipient name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^City/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Postal code/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Country/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Pickup day" })).not.toBeInTheDocument();
  });

  it("renders both the pickup picker and the address form for a mixed cart", async () => {
    stubFetch(mixedCart);

    renderWithProviders(<CheckoutPage />);

    expect(await screen.findByRole("group", { name: "Pickup day" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Recipient name/)).toBeInTheDocument();
  });

  it("keeps the submit button disabled until a pickup slot is chosen", async () => {
    stubFetch(pickupOnlyCart);

    renderWithProviders(<CheckoutPage />);

    const button = await screen.findByRole("button", { name: /Continue to payment/ });
    expect(button).toBeDisabled();

    const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
    fireEvent.click(within(slotGroup).getAllByRole("button")[0]);

    expect(button).not.toBeDisabled();
  });

  it("submits the chosen pickup slot as pickup_at", async () => {
    const fetchMock = stubFetch(pickupOnlyCart);
    const assignSpy = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: assignSpy },
    });

    try {
      const { container } = renderWithProviders(<CheckoutPage />);
      fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
      const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
      fireEvent.click(within(slotGroup).getAllByRole("button")[1]);
      submitForm(container);

      await vi.waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith("/api/v1/checkout", expect.objectContaining({ method: "POST" })),
      );
      const checkoutCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).includes("/checkout") && init?.method === "POST",
      );
      const body = JSON.parse(checkoutCall![1]!.body as string);
      expect(body).toEqual({
        email: "shopper@example.com",
        pickup_at: "2026-07-09T16:15:00Z",
        payment_method: "online",
      });
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
    }
  });

  it("shows a validation error and does not call the API when the retail form is submitted empty", async () => {
    stubFetch(retailOnlyCart);

    const { container } = renderWithProviders(<CheckoutPage />);
    await screen.findByLabelText(/Recipient name/);
    submitForm(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("Email is required.");
  });

  it("shows an error state when checkout fails (e.g. insufficient stock)", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/storefront-config")) {
        return Promise.resolve(new Response(JSON.stringify({ online_payments_enabled: true }), { status: 200 }));
      }
      if (url.includes("/cart")) {
        return Promise.resolve(new Response(JSON.stringify(retailOnlyCart), { status: 200 }));
      }
      if (url.includes("/checkout") && init?.method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Insufficient stock for one or more items." }), { status: 409 }),
        );
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderWithProviders(<CheckoutPage />);
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    fireEvent.change(screen.getByLabelText(/Recipient name/), { target: { value: "Ada Lovelace" } });
    fireEvent.change(screen.getByLabelText(/Address/), { target: { value: "1 Analytical Engine Rd" } });
    fireEvent.change(screen.getByLabelText(/^City/), { target: { value: "Umeå" } });
    fireEvent.change(screen.getByLabelText(/Postal code/), { target: { value: "90325" } });
    submitForm(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("Insufficient stock for one or more items.");
  });

  it("shows a friendly message and refetches pickup days when a slot fills up between render and submit", async () => {
    let checkoutAttempt = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/storefront-config")) {
        return Promise.resolve(new Response(JSON.stringify({ online_payments_enabled: true }), { status: 200 }));
      }
      if (url.includes("/pickup-days")) {
        return Promise.resolve(new Response(JSON.stringify(pickupDays), { status: 200 }));
      }
      if (url.includes("/cart")) {
        return Promise.resolve(new Response(JSON.stringify(pickupOnlyCart), { status: 200 }));
      }
      if (url.includes("/checkout") && init?.method === "POST") {
        checkoutAttempt += 1;
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "That pickup slot is no longer available." }), { status: 409 }),
        );
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderWithProviders(<CheckoutPage />);
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
    fireEvent.click(within(slotGroup).getAllByRole("button")[1]);
    submitForm(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("That time just filled up — pick another.");
    expect(checkoutAttempt).toBe(1);
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("/pickup-days")).length).toBeGreaterThan(1),
    );
  });

  it("offers a pay-at-pickup vs pay-online choice for a pickup-only cart", async () => {
    stubFetch(pickupOnlyCart);

    renderWithProviders(<CheckoutPage />);

    const radioGroup = await screen.findByRole("radiogroup", { name: "Payment method" });
    expect(within(radioGroup).getByLabelText(/Pay online now/)).toBeChecked();
    expect(within(radioGroup).getByLabelText(/Pay at pickup/)).not.toBeChecked();
  });

  it("does not offer a payment choice when the cart needs shipping", async () => {
    stubFetch(retailOnlyCart);

    renderWithProviders(<CheckoutPage />);

    await screen.findByLabelText(/Recipient name/);
    expect(screen.queryByRole("radiogroup", { name: "Payment method" })).not.toBeInTheDocument();
  });

  it("does not offer a payment choice for a mixed cart (pickup + shipping)", async () => {
    stubFetch(mixedCart);

    renderWithProviders(<CheckoutPage />);

    await screen.findByRole("group", { name: "Pickup day" });
    expect(screen.queryByRole("radiogroup", { name: "Payment method" })).not.toBeInTheDocument();
  });

  it("sends payment_method: pay_at_pickup and adapts the submit label when chosen", async () => {
    const fetchMock = stubFetch(pickupOnlyCart);
    const assignSpy = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: assignSpy },
    });

    try {
      const { container } = renderWithProviders(<CheckoutPage />);
      fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
      const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
      fireEvent.click(within(slotGroup).getAllByRole("button")[0]);
      fireEvent.click(screen.getByLabelText(/Pay at pickup/));

      expect(screen.getByRole("button", { name: "Confirm order — pay at pickup" })).toBeInTheDocument();

      submitForm(container);

      await vi.waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith("/api/v1/checkout", expect.objectContaining({ method: "POST" })),
      );
      const checkoutCall = fetchMock.mock.calls.find(
        ([input, init]) => String(input).includes("/checkout") && init?.method === "POST",
      );
      const body = JSON.parse(checkoutCall![1]!.body as string);
      expect(body.payment_method).toBe("pay_at_pickup");
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
    }
  });

  it("navigates to /thanks (not checkout_url) after a successful pay-at-pickup order", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/storefront-config")) {
        return Promise.resolve(new Response(JSON.stringify({ online_payments_enabled: true }), { status: 200 }));
      }
      if (url.includes("/pickup-days")) {
        return Promise.resolve(new Response(JSON.stringify(pickupDays), { status: 200 }));
      }
      if (url.includes("/cart")) {
        return Promise.resolve(new Response(JSON.stringify(pickupOnlyCart), { status: 200 }));
      }
      if (url.includes("/checkout") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              order_id: "order-1",
              display_number: "M-0001",
              checkout_url: "http://localhost:5173/orders/order-1",
              guest_lookup_token: "guest-token",
              reservation_expires_at: null,
            }),
            { status: 201 },
          ),
        );
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const assignSpy = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: assignSpy },
    });

    try {
      const { container } = render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter initialEntries={["/checkout"]}>
            <Routes>
              <Route path="/checkout" element={<CheckoutPage />} />
              <Route path="/thanks" element={<div>Thanks page</div>} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
      const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
      fireEvent.click(within(slotGroup).getAllByRole("button")[0]);
      fireEvent.click(screen.getByLabelText(/Pay at pickup/));
      submitForm(container);

      expect(await screen.findByText("Thanks page")).toBeInTheDocument();
      expect(assignSpy).not.toHaveBeenCalled();
      expect(sessionStorage.getItem("guestOrderToken")).toBe("guest-token");
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
    }
  });

  it("shows a friendly message when no pickup times are open at all", async () => {
    stubFetch(pickupOnlyCart, []);

    renderWithProviders(<CheckoutPage />);

    expect(
      await screen.findByText("No pickup times are open right now — check back soon, or message us."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Pickup day" })).not.toBeInTheDocument();
    const button = screen.getByRole("button", { name: /Continue to payment/ });
    expect(button).toBeDisabled();
  });

  it("hides the email input and shows a receipt line when signed in", async () => {
    stubFetch(retailOnlyCart, pickupDays, { signedIn: true });

    renderWithProviders(<CheckoutPage />);

    expect(await screen.findByText(/Receipt goes to account@example.com/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^Email/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Not you\? Sign out/ })).toHaveAttribute("href", "/account");
  });

  it("checks out while signed in without requiring the email field", async () => {
    const fetchMock = stubFetch(retailOnlyCart, pickupDays, { signedIn: true });

    const { container } = renderWithProviders(<CheckoutPage />);
    await screen.findByText(/Receipt goes to account@example.com/);
    fireEvent.change(screen.getByLabelText(/Recipient name/), { target: { value: "Ada Lovelace" } });
    fireEvent.change(screen.getByLabelText(/Address/), { target: { value: "1 Analytical Engine Rd" } });
    fireEvent.change(screen.getByLabelText(/^City/), { target: { value: "Umeå" } });
    fireEvent.change(screen.getByLabelText(/Postal code/), { target: { value: "90325" } });
    submitForm(container);

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/checkout", expect.objectContaining({ method: "POST" })),
    );
    const checkoutCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).includes("/checkout") && init?.method === "POST",
    );
    const body = JSON.parse(checkoutCall![1]!.body as string);
    expect(body.email).toBeUndefined();
  });

  it("sends a trimmed contact_handle when filled in", async () => {
    const fetchMock = stubFetch(retailOnlyCart);

    const { container } = renderWithProviders(<CheckoutPage />);
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    fireEvent.change(screen.getByLabelText(/Telegram or WhatsApp/), { target: { value: "  @shopper_tg  " } });
    fireEvent.change(screen.getByLabelText(/Recipient name/), { target: { value: "Ada Lovelace" } });
    fireEvent.change(screen.getByLabelText(/Address/), { target: { value: "1 Analytical Engine Rd" } });
    fireEvent.change(screen.getByLabelText(/^City/), { target: { value: "Umeå" } });
    fireEvent.change(screen.getByLabelText(/Postal code/), { target: { value: "90325" } });
    submitForm(container);

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/checkout", expect.objectContaining({ method: "POST" })),
    );
    const checkoutCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).includes("/checkout") && init?.method === "POST",
    );
    const body = JSON.parse(checkoutCall![1]!.body as string);
    expect(body.contact_handle).toBe("@shopper_tg");
  });

  it("shows a hint under the submit button when no pickup slot is chosen yet", async () => {
    stubFetch(pickupOnlyCart);

    renderWithProviders(<CheckoutPage />);

    await screen.findByRole("group", { name: "Pickup day" });
    expect(screen.getByText("Choose a pickup time above to continue.")).toBeInTheDocument();

    const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
    fireEvent.click(within(slotGroup).getAllByRole("button")[0]);

    expect(screen.queryByText("Choose a pickup time above to continue.")).not.toBeInTheDocument();
  });

  it("hides the payment radio and shows pay-at-pickup info when online payments are disabled", async () => {
    stubFetch(pickupOnlyCart, pickupDays, { onlinePaymentsEnabled: false });

    renderWithProviders(<CheckoutPage />);

    await screen.findByRole("group", { name: "Pickup day" });
    expect(screen.queryByRole("radiogroup", { name: "Payment method" })).not.toBeInTheDocument();
    expect(screen.getByText(/Pay when you collect/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm order — pay at pickup" })).toBeInTheDocument();
  });

  it("submits payment_method: pay_at_pickup when online payments are disabled", async () => {
    const fetchMock = stubFetch(pickupOnlyCart, pickupDays, { onlinePaymentsEnabled: false });

    const { container } = renderWithProviders(<CheckoutPage />);
    fireEvent.change(await screen.findByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    const slotGroup = await screen.findByRole("group", { name: "Pickup time slot" });
    fireEvent.click(within(slotGroup).getAllByRole("button")[0]);
    submitForm(container);

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/checkout", expect.objectContaining({ method: "POST" })),
    );
    const checkoutCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).includes("/checkout") && init?.method === "POST",
    );
    const body = JSON.parse(checkoutCall![1]!.body as string);
    expect(body.payment_method).toBe("pay_at_pickup");
  });
});
