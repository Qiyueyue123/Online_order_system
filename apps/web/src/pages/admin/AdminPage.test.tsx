import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminPage } from "./AdminPage";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function sessionResponse(role: string) {
  return new Response(
    JSON.stringify({
      user: { id: "user-1", email: "person@example.com", name: "Person", role, email_verified: true },
      csrf_token: "csrf-token-1",
    }),
    { status: 200 },
  );
}

describe("AdminPage access control", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a not-authorized state and fires no admin requests for a non-admin session", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/auth/session")) return Promise.resolve(sessionResponse("customer"));
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminPage />);

    expect(await screen.findByText("Not authorized")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.every(([input]) => !String(input).includes("/admin"))).toBe(true);
  });

  it("renders the admin tabs and defaults to the Orders view for an admin session", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/auth/session")) return Promise.resolve(sessionResponse("admin"));
      if (url.includes("/admin/orders")) {
        return Promise.resolve(
          new Response(JSON.stringify({ items: [], page: 1, page_size: 50, total: 0 }), { status: 200 }),
        );
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminPage />);

    expect(await screen.findByRole("tab", { name: "Orders" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Products" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Pickup days" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Audit log" })).toBeInTheDocument();
  });
});
