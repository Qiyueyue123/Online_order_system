import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MediaCarousel, MediaCarouselItem } from "./MediaCarousel";

const twoItems: MediaCarouselItem[] = [
  { url: "/media/a.jpg", alt_text: "First photo", media_type: "image" },
  { url: "/media/b.jpg", alt_text: "Second photo", media_type: "image" },
];

const oneItem: MediaCarouselItem[] = [{ url: "/media/a.jpg", alt_text: "Only photo", media_type: "image" }];

function stubMatchMedia(reduced: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: reduced,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

describe("MediaCarousel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
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

  it("auto-advances to the next item after 5 seconds with 2+ items", () => {
    stubMatchMedia(false);
    vi.useFakeTimers();
    render(<MediaCarousel items={twoItems} />);

    expect(screen.getByAltText("First photo").closest(".media-carousel-slide")).toHaveClass("is-active");

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(screen.getByAltText("Second photo").closest(".media-carousel-slide")).toHaveClass("is-active");
  });

  it("does not auto-advance when the user prefers reduced motion", () => {
    stubMatchMedia(true);
    vi.useFakeTimers();
    render(<MediaCarousel items={twoItems} />);

    expect(screen.getByAltText("First photo").closest(".media-carousel-slide")).toHaveClass("is-active");

    vi.advanceTimersByTime(10000);

    expect(screen.getByAltText("First photo").closest(".media-carousel-slide")).toHaveClass("is-active");
  });

  it("shows the active item's caption only when showCaptions is set", () => {
    const items = [
      { url: "/media/a.jpg", alt_text: "First photo", media_type: "image", caption: "Whisked to order" },
      { url: "/media/b.jpg", alt_text: "Second photo", media_type: "image" },
    ];

    const { rerender } = render(<MediaCarousel items={items} />);
    expect(screen.queryByText("Whisked to order")).not.toBeInTheDocument();

    rerender(<MediaCarousel items={items} showCaptions />);
    expect(screen.getByText("Whisked to order")).toBeInTheDocument();
  });
});
