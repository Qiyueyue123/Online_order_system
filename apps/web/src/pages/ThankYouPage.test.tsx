import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ThankYouPage } from "./ThankYouPage";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ThankYouPage />
    </MemoryRouter>,
  );
}

describe("ThankYouPage", () => {
  it("shows the order number and formatted pickup time when both are given", () => {
    renderAt("/thanks?order=M-0001&pickup=2026-07-09T16:15:00Z");

    expect(screen.getByText(/Thanks/)).toHaveTextContent("Thanks — your order M-0001 is in.");
    expect(screen.getByText(/Pickup/)).toHaveTextContent("Pickup");
    expect(screen.getByText(/confirmation email/)).toBeInTheDocument();
  });

  it("handles missing query params gracefully", () => {
    renderAt("/thanks");

    expect(screen.getByText("Thanks — your order is in.")).toBeInTheDocument();
    expect(screen.queryByText(/Pickup /)).not.toBeInTheDocument();
  });

  it("links contact handles and back to home", () => {
    renderAt("/thanks?order=M-0001");

    expect(screen.getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "@notqiyue" })).toHaveAttribute("href", "https://t.me/notqiyue");
    expect(screen.getByRole("link", { name: "+65 9788 8146" })).toHaveAttribute(
      "href",
      "https://wa.me/6597888146",
    );
  });
});
