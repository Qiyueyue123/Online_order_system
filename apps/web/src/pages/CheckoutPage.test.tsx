import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CheckoutPage } from "./CheckoutPage";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function fillAddressFields() {
  fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "shopper@example.com" } });
  fireEvent.change(screen.getByLabelText(/Recipient name/), { target: { value: "Ada Lovelace" } });
  fireEvent.change(screen.getByLabelText(/Address/), { target: { value: "1 Analytical Engine Rd" } });
  fireEvent.change(screen.getByLabelText(/City/), { target: { value: "Singapore" } });
  fireEvent.change(screen.getByLabelText(/Postal code/), { target: { value: "123456" } });
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

  it("renders the shipping address form fields", () => {
    renderWithProviders(<CheckoutPage />);

    expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Recipient name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Address/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^City/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Postal code/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Country/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue to Stripe test checkout/ })).toBeInTheDocument();
  });

  it("shows a validation error and does not call the API when submitted empty", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderWithProviders(<CheckoutPage />);

    submitForm(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("Email is required.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits the address payload to /checkout and follows the redirect on success", async () => {
    const result = { checkout_url: "https://stripe.example.com/session/abc", guest_lookup_token: "guest-token-1" };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const assignSpy = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: assignSpy },
    });

    try {
      const { container } = renderWithProviders(<CheckoutPage />);
      fillAddressFields();
      submitForm(container);

      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/checkout",
        expect.objectContaining({ method: "POST" }),
      );
      const [, requestInit] = fetchMock.mock.calls[0];
      const body = JSON.parse(requestInit.body as string);
      expect(body).toEqual({
        email: "shopper@example.com",
        shipping_address: {
          email: undefined,
          recipient_name: "Ada Lovelace",
          line1: "1 Analytical Engine Rd",
          city: "Singapore",
          postal_code: "123456",
          country_code: "SG",
        },
      });

      await vi.waitFor(() => expect(assignSpy).toHaveBeenCalledWith(result.checkout_url));
      expect(sessionStorage.getItem("guestOrderToken")).toBe("guest-token-1");
    } finally {
      Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
    }
  });

  it("shows an error state when checkout fails (e.g. insufficient stock)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Insufficient stock for one or more items." }), { status: 409 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderWithProviders(<CheckoutPage />);
    fillAddressFields();
    submitForm(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("Insufficient stock for one or more items.");
  });
});
