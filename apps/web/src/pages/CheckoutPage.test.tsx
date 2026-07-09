import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
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
      variant_id: "var-1",
      product_slug: "sayaka-latte",
      product_name: "Sayaka Latte",
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

function stubFetch(cart: Cart, days: PickupDay[] = pickupDays) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
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

    const button = await screen.findByRole("button", { name: /Continue to Stripe test checkout/ });
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
      expect(body).toEqual({ email: "shopper@example.com", pickup_at: "2026-07-09T16:15:00Z" });
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
});
