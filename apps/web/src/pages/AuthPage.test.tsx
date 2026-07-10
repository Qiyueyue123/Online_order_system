import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Session } from "../api/client";
import { AuthPage } from "./AuthPage";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigateMock };
});

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function submitForm(container: HTMLElement) {
  const form = container.querySelector("form");
  if (!form) throw new Error("form not found");
  fireEvent.submit(form);
}

const session: Session = {
  user: { id: "user-1", email: "shopper@example.com", name: "Ada Lovelace" },
} as Session;

describe("AuthPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    navigateMock.mockClear();
  });

  it("defaults to login mode and toggles to register mode and back", () => {
    renderWithProviders(<AuthPage />);

    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Name/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Need an account\? Register/ }));

    expect(screen.getByRole("heading", { name: "Create an account." })).toBeInTheDocument();
    expect(screen.getByLabelText(/Name/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Register" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Already registered\? Sign in/ }));

    expect(screen.getByRole("heading", { name: "Welcome back." })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Name/)).not.toBeInTheDocument();
  });

  it("posts login credentials and navigates to /account on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(session), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderWithProviders(<AuthPage />);

    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "hunter2" } });
    submitForm(container);

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      expect.objectContaining({ method: "POST" }),
    );
    const [, requestInit] = fetchMock.mock.calls[0];
    expect(JSON.parse(requestInit.body as string)).toEqual({
      email: "shopper@example.com",
      password: "hunter2",
    });

    await vi.waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/account"));
  });

  it("shows an error message when login fails with 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid email or password." }), { status: 401 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { container } = renderWithProviders(<AuthPage />);

    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "shopper@example.com" } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "wrong-password" } });
    submitForm(container);

    expect(await screen.findByRole("alert")).toHaveTextContent("Check your email and password and try again.");
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
