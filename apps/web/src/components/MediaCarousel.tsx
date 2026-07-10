import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

export type MediaCarouselItem = {
  url: string;
  alt_text: string;
  media_type: "image" | "video" | string;
};

/**
 * Reusable photo/video carousel: arrow buttons, dot indicators, and a
 * crossfade between stacked absolutely-positioned slides — the same idea as
 * HeroCarousel, but user-driven (no auto-rotation) and usable either
 * uncontrolled (its own state) or controlled (e.g. synced with thumbnail
 * buttons on the product page via `activeIndex`/`onActiveIndexChange`).
 */
export function MediaCarousel({
  items,
  activeIndex,
  onActiveIndexChange,
  mediaClassName = "",
  label = "Product media",
  eagerFirst = false,
}: {
  items: MediaCarouselItem[];
  activeIndex?: number;
  onActiveIndexChange?: (index: number) => void;
  mediaClassName?: string;
  label?: string;
  /** Load the first slide eagerly — for a single above-the-fold gallery, not a grid of cards. */
  eagerFirst?: boolean;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const [internalIndex, setInternalIndex] = useState(0);
  const active = activeIndex !== undefined ? activeIndex % items.length : internalIndex;
  const videoRefs = useRef<Record<number, HTMLVideoElement | null>>({});

  function setActive(index: number) {
    const wrapped = (index + items.length) % items.length;
    if (onActiveIndexChange) onActiveIndexChange(wrapped);
    else setInternalIndex(wrapped);
  }

  useEffect(() => {
    Object.entries(videoRefs.current).forEach(([key, video]) => {
      if (!video) return;
      const index = Number(key);
      try {
        if (index === active) {
          video.currentTime = 0;
          video.play()?.catch(() => {});
        } else {
          video.pause();
        }
      } catch {
        // Media APIs are unimplemented in some test/SSR environments (jsdom);
        // this carousel is otherwise fully functional without playback.
      }
    });
  }, [active]);

  if (items.length === 0) return null;

  return (
    <div className="media-carousel">
      {items.map((item, index) => {
        const isActive = index === active;
        if (reducedMotion && !isActive) return null;
        return (
          <div
            className={`media-carousel-slide${isActive ? " is-active" : ""}`}
            key={item.url}
            aria-hidden={!isActive}
          >
            {item.media_type === "video" ? (
              <video
                ref={(el) => {
                  videoRefs.current[index] = el;
                }}
                className={mediaClassName}
                src={item.url}
                muted
                loop
                playsInline
                autoPlay={isActive}
                aria-label={item.alt_text}
              />
            ) : (
              <img
                className={mediaClassName}
                src={item.url}
                alt={item.alt_text}
                loading={eagerFirst && index === 0 ? "eager" : "lazy"}
              />
            )}
          </div>
        );
      })}
      {items.length > 1 && (
        <>
          <button
            type="button"
            className="media-carousel-arrow media-carousel-arrow--prev"
            aria-label="Previous photo"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setActive(active - 1);
            }}
          >
            ‹
          </button>
          <button
            type="button"
            className="media-carousel-arrow media-carousel-arrow--next"
            aria-label="Next photo"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              setActive(active + 1);
            }}
          >
            ›
          </button>
          <div className="media-carousel-dots" role="group" aria-label={label}>
            {items.map((item, index) => (
              <button
                type="button"
                key={item.url}
                className={`media-carousel-dot${index === active ? " active" : ""}`}
                aria-label={`Show item ${index + 1}`}
                aria-pressed={index === active}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setActive(index);
                }}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
