import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AdminPickupDay } from "../../api/client";
import { AdminPickupDays } from "./AdminPickupDays";

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const days: AdminPickupDay[] = [
  {
    id: "day-1",
    date: "2026-07-09",
    start_time: "16:00:00",
    end_time: "19:00:00",
    slot_minutes: 15,
    slot_capacity: 2,
    is_available: true,
  },
];

describe("AdminPickupDays", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the list of upcoming pickup days", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(days), { status: 200 })));

    renderWithProviders(<AdminPickupDays csrfToken="csrf-token-1" />);

    expect(await screen.findByText("2026-07-09")).toBeInTheDocument();
    expect(screen.getByText("16:00:00–19:00:00")).toBeInTheDocument();
    expect(screen.getByText("15 min")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
  });

  it("creates a pickup day from the form and refreshes the list", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify(days[0]), { status: 201 }));
      }
      if (url.includes("/admin/pickup-days")) {
        return Promise.resolve(new Response(JSON.stringify(days), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<AdminPickupDays csrfToken="csrf-token-1" />);
    await screen.findByText("2026-07-09");

    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-07-11" } });
    fireEvent.click(screen.getByRole("button", { name: /Add pickup day/ }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/pickup-days",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    const body = JSON.parse(postCall![1]!.body as string);
    expect(body).toEqual({
      date: "2026-07-11",
      start_time: "16:00",
      end_time: "19:00",
      slot_minutes: 15,
      slot_capacity: 2,
    });
  });

  it("toggles availability with the X-CSRF-Token header once confirmed", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (init?.method === "PATCH") {
        return Promise.resolve(new Response(JSON.stringify({ ...days[0], is_available: false }), { status: 200 }));
      }
      if (url.includes("/admin/pickup-days")) {
        return Promise.resolve(new Response(JSON.stringify(days), { status: 200 }));
      }
      throw new Error(`Unexpected fetch to ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWithProviders(<AdminPickupDays csrfToken="csrf-token-1" />);
    await screen.findByText("2026-07-09");

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    await vi.waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/admin/pickup-days/day-1",
        expect.objectContaining({
          method: "PATCH",
          headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token-1" }),
        }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(patchCall![1]!.body as string)).toEqual({ is_available: false });
  });

  it("does not disable a pickup day when the confirm prompt is dismissed", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(days), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    renderWithProviders(<AdminPickupDays csrfToken="csrf-token-1" />);
    await screen.findByText("2026-07-09");

    fireEvent.click(screen.getByRole("button", { name: "Disable" }));

    expect(confirmSpy).toHaveBeenCalled();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });
});
