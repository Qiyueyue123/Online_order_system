import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MediaCarousel, MediaCarouselItem } from "./MediaCarousel";

const twoItems: MediaCarouselItem[] = [
  { url: "/media/a.jpg", alt_text: "First photo", media_type: "image" },
  { url: "/media/b.jpg", alt_text: "Second photo", media_type: "image" },
];

const oneItem: MediaCarouselItem[] = [{ url: "/media/a.jpg", alt_text: "Only photo", media_type: "image" }];

const videoItem: MediaCarouselItem[] = [
  { url: "/media/clip.mp4", alt_text: "Whisking video", media_type: "video" },
  { url: "/media/b.jpg", alt_text: "Second photo", media_type: "image" },
];

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

  it("renders a mute toggle on the active video slide, starts muted, and toggles on click", () => {
    render(<MediaCarousel items={videoItem} />);

    const toggle = screen.getByRole("button", { name: "Unmute video" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");

    const video = screen.getByLabelText("Whisking video") as HTMLVideoElement;
    expect(video.muted).toBe(true);

    fireEvent.click(toggle);

    expect(video.muted).toBe(false);
    expect(screen.getByRole("button", { name: "Mute video" })).toHaveAttribute("aria-pressed", "true");
  });

  it("does not render mute toggle or progress bar for image slides", () => {
    render(<MediaCarousel items={twoItems} />);
    expect(screen.queryByRole("button", { name: /mute video/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: "Video progress" })).not.toBeInTheDocument();
  });

  it("stops propagation so the mute toggle does not trigger a wrapping card click", () => {
    const onCardClick = vi.fn();
    render(
      <div onClick={onCardClick}>
        <MediaCarousel items={videoItem} />
      </div>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Unmute video" }));

    expect(onCardClick).not.toHaveBeenCalled();
  });

  it("seeks on progress bar click and stops propagation", () => {
    const onCardClick = vi.fn();
    render(
      <div onClick={onCardClick}>
        <MediaCarousel items={videoItem} />
      </div>,
    );

    const video = screen.getByLabelText("Whisking video") as HTMLVideoElement;
    Object.defineProperty(video, "duration", { value: 100, configurable: true });
    Object.defineProperty(video, "currentTime", { value: 0, writable: true, configurable: true });

    const progress = screen.getByRole("slider", { name: "Video progress" });
    vi.spyOn(progress, "getBoundingClientRect").mockReturnValue({
      left: 0,
      right: 200,
      width: 200,
      top: 0,
      bottom: 10,
      height: 10,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });

    fireEvent.click(progress, { clientX: 50 });

    expect(video.currentTime).toBe(25);
    expect(progress).toHaveAttribute("aria-valuenow", "25");
    expect(onCardClick).not.toHaveBeenCalled();
  });

  it("seeks +/-5s with arrow keys on the focused progress bar", () => {
    render(<MediaCarousel items={videoItem} />);

    const video = screen.getByLabelText("Whisking video") as HTMLVideoElement;
    Object.defineProperty(video, "duration", { value: 100, configurable: true });
    Object.defineProperty(video, "currentTime", { value: 10, writable: true, configurable: true });

    const progress = screen.getByRole("slider", { name: "Video progress" });
    fireEvent.keyDown(progress, { key: "ArrowRight" });
    expect(video.currentTime).toBe(15);

    fireEvent.keyDown(progress, { key: "ArrowLeft" });
    expect(video.currentTime).toBe(10);
  });

  it("updates the progress bar as the video plays via timeupdate", () => {
    render(<MediaCarousel items={videoItem} />);

    const video = screen.getByLabelText("Whisking video") as HTMLVideoElement;
    Object.defineProperty(video, "duration", { value: 40, configurable: true });
    Object.defineProperty(video, "currentTime", { value: 10, writable: true, configurable: true });

    fireEvent.timeUpdate(video);

    expect(screen.getByRole("slider", { name: "Video progress" })).toHaveAttribute("aria-valuenow", "25");
  });
});
