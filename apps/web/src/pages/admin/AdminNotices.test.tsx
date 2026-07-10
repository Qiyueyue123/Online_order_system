import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AdminNotice } from "../../api/client";
import { AdminNotices } from "./AdminNotices";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const notices: AdminNotice[] = [
  {
    id: "notice-1",
    title: "Closed Monday",
    body: "We're closed for a private event on Monday.",
    active: true,
    created_at: "2026-07-09T10:00:00Z",
    updated_at: "2026-07-09T10:00:00Z",
  },
];

describe("AdminNotices", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the list of notices", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(notices), { status: 200 })),
    );

    renderWithProviders(<AdminNotices csrfToken="csrf-token-1" />);

    expect(await screen.findByText("Closed Monday")).toBeInTheDocument();
    expect(screen.getByText("We're closed for a private event on Monday.")).toBeInTheDocument();
  });

  it("creates a notice from the form and refreshes the list", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify(notices[0]), { status: 201 }));
      }
      if (url.includes("/admin/notices")) {
        return Promise.resolve(new Response(JSON.stringify(notices), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminNotices csrfToken="csrf-token-1" />);
    await screen.findByText("Closed Monday");

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "New notice" } });
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Body text" } });
    fireEvent.click(screen.getByRole("button", { name: /Post notice/ }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/notices",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    const body = JSON.parse(postCall![1]!.body as string);
    expect(body).toEqual({ title: "New notice", body: "Body text" });
  });

  it("toggles visibility with the X-CSRF-Token header", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(new Response(JSON.stringify({ ...notices[0], active: false }), { status: 200 }));
      }
      if (url.includes("/admin/notices")) {
        return Promise.resolve(new Response(JSON.stringify(notices), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminNotices csrfToken="csrf-token-1" />);
    await screen.findByText("Closed Monday");

    fireEvent.click(screen.getByRole("button", { name: "Hide" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/notices/notice-1",
        expect.objectContaining({
          method: "PATCH",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(patchCall![1]!.body as string)).toEqual({ active: false });
  });

  it("deletes a notice only after the confirm prompt is accepted", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.includes("/admin/notices")) {
        return Promise.resolve(new Response(JSON.stringify(notices), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    renderWithProviders(<AdminNotices csrfToken="csrf-token-1" />);
    await screen.findByText("Closed Monday");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);

    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true),
    );
  });
});
