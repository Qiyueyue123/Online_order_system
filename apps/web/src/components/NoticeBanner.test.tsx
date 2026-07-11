import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NoticeBanner } from "./NoticeBanner";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("NoticeBanner", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders active notices", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
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
        ),
      ),
    );

    renderWithProviders(<NoticeBanner />);

    expect(await screen.findByText("Closed this weekend")).toBeInTheDocument();
    expect(
      screen.getByText("We're away at a matcha festival — back Monday."),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Shop notices" })).toBeInTheDocument();
  });

  it("renders nothing when there are no notices", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))),
    );

    const { container } = renderWithProviders(<NoticeBanner />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("renders nothing when the notices request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "nope" }), { status: 500 }))),
    );

    const { container } = renderWithProviders(<NoticeBanner />);

    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(screen.queryByRole("region", { name: "Shop notices" })).not.toBeInTheDocument();
  });
});
