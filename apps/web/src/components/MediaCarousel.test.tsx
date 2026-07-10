import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MediaCarousel, MediaCarouselItem } from "./MediaCarousel";

const twoItems: MediaCarouselItem[] = [
  { url: "/media/a.jpg", alt_text: "First photo", media_type: "image" },
  { url: "/media/b.jpg", alt_text: "Second photo", media_type: "image" },
];

const oneItem: MediaCarouselItem[] = [{ url: "/media/a.jpg", alt_text: "Only photo", media_type: "image" }];

describe("MediaCarousel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders no arrows or dots for a single item", () => {
    render(<MediaCarousel items={oneItem} />);
    expect(screen.queryByRole("button", { name: "Next photo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Previous photo" })).not.toBeInTheDocument();
    expect(screen.getByAltText("Only photo")).toBeInTheDocument();
  });

  it("cycles the active item with the arrow buttons", () => {
    render(<MediaCarousel items={twoItems} />);

    expect(screen.getByAltText("First photo").closest(".media-carousel-slide")).toHaveClass("is-active");

    fireEvent.click(screen.getByRole("button", { name: "Next photo" }));
    expect(screen.getByAltText("Second photo").closest(".media-carousel-slide")).toHaveClass("is-active");

    fireEvent.click(screen.getByRole("button", { name: "Previous photo" }));
    expect(screen.getByAltText("First photo").closest(".media-carousel-slide")).toHaveClass("is-active");
  });

  it("jumps to an item when its dot is clicked, and reports the change when controlled", () => {
    const onActiveIndexChange = vi.fn();
    render(<MediaCarousel items={twoItems} activeIndex={0} onActiveIndexChange={onActiveIndexChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Show item 2" }));

    expect(onActiveIndexChange).toHaveBeenCalledWith(1);
  });
});
