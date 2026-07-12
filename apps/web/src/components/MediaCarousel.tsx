import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

export type MediaCarouselItem = {
  url: string;
  alt_text: string;
  media_type: "image" | "video" | string;
  caption?: string | null;
};

const AUTO_ADVANCE_MS = 5000;

/**
 * Reusable photo/video carousel: arrow buttons, dot indicators, and a
 * crossfade between stacked absolutely-positioned slides — the same idea as
 * HeroCarousel. Auto-advances every ~5s when it has 2+ items, pausing on
 * hover/focus and resetting after any manual interaction; a video slide
 * holds the timer and instead advances when it finishes playing. Usable
 * either uncontrolled (its own state) or controlled (e.g. synced with
 * thumbnail buttons on the product page via `activeIndex`/`onActiveIndexChange`).
 */
export function MediaCarousel({
  items,
  activeIndex,
  onActiveIndexChange,
  mediaClassName = "",
  label = "Product media",
  eagerFirst = false,
  showCaptions = false,
}: {
  items: MediaCarouselItem[];
  activeIndex?: number;
  onActiveIndexChange?: (index: number) => void;
  mediaClassName?: string;
  label?: string;
  /** Load the first slide eagerly — for a single above-the-fold gallery, not a grid of cards. */
  eagerFirst?: boolean;
  /** Show the active item's caption in a bar under the media. Off by default to avoid clutter on small cards. */
  showCaptions?: boolean;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const [internalIndex, setInternalIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const active = activeIndex !== undefined ? activeIndex % items.length : internalIndex;
  const videoRefs = useRef<Record<number, HTMLVideoElement | null>>({});

  // Per-slide mute state for the unmute toggle. Undefined/missing entries
  // default to muted (true) -- matches the video element's own initial
  // `muted` attribute below, and keeps unmuting one slide from leaking into
  // another when the active slide changes.
  const [mutedState, setMutedState] = useState<Record<number, boolean>>({});
  const isMuted = (index: number) => mutedState[index] ?? true;
  const [activeProgress, setActiveProgress] = useState(0);

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
          // Browsers only allow autoplay when the video starts muted; the
          // unmute toggle then flips `video.muted` imperatively after the
          // user opts in.
          video.muted = true;
          video.play()?.catch(() => {});
        } else {
          video.pause();
        }
      } catch {
        // Media APIs are unimplemented in some test/SSR environments (jsdom);
        // this carousel is otherwise fully functional without playback.
      }
    });
    setMutedState((prev) => (prev[active] === true ? prev : { ...prev, [active]: true }));
    setActiveProgress(0);
  }, [active]);

  const activeItem = items[active] as MediaCarouselItem | undefined;
  const activeIsVideo = activeItem?.media_type === "video";
  // While the active video is unmuted, treat the carousel as paused --
  // reuses the same gate hover/focus use below -- so a listening customer
  // isn't cut off mid-clip. Re-muting or the video ending clears it again.
  const unmutedPause = activeIsVideo && !isMuted(active);

  // Auto-advance on a timer, unless reduced motion is on, there's only one
  // item, the carousel is paused (hover/focus/unmuted video), or the active
  // slide is a video -- videos advance via their own `ended` event below
  // instead.
  useEffect(() => {
    if (reducedMotion || paused || unmutedPause || items.length < 2 || activeIsVideo) return;
    const id = window.setTimeout(() => setActive(active + 1), AUTO_ADVANCE_MS);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, reducedMotion, paused, unmutedPause, items.length, activeIsVideo]);

  function handleVideoEnded(index: number) {
    if (reducedMotion || paused || unmutedPause || items.length < 2 || index !== active) return;
    setActive(active + 1);
  }

  function toggleMute(index: number) {
    const video = videoRefs.current[index];
    const nextMuted = !isMuted(index);
    if (video) video.muted = nextMuted;
    setMutedState((prev) => ({ ...prev, [index]: nextMuted }));
  }

  function seekBy(index: number, deltaSeconds: number) {
    const video = videoRefs.current[index];
    if (!video || !Number.isFinite(video.duration)) return;
    const nextTime = Math.min(video.duration, Math.max(0, video.currentTime + deltaSeconds));
    video.currentTime = nextTime;
    setActiveProgress((nextTime / video.duration) * 100);
  }

  function seekToClientX(index: number, clientX: number, target: HTMLElement) {
    const video = videoRefs.current[index];
    if (!video || !Number.isFinite(video.duration) || video.duration === 0) return;
    const rect = target.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    video.currentTime = fraction * video.duration;
    setActiveProgress(fraction * 100);
  }

  if (items.length === 0) return null;

  return (
    <div
      className={`media-carousel${showCaptions && activeItem?.caption ? " media-carousel--has-caption" : ""}${activeIsVideo ? " media-carousel--has-progress" : ""}`}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setPaused(false);
      }}
    >
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
                // Autoplay policy requires the video to start muted; the
                // unmute toggle below then flips `video.muted` directly.
                muted
                loop={items.length < 2}
                playsInline
                autoPlay={isActive}
                aria-label={item.alt_text}
                onEnded={() => handleVideoEnded(index)}
                onTimeUpdate={(event) => {
                  if (index !== active) return;
                  const video = event.currentTarget;
                  if (!video.duration) return;
                  setActiveProgress((video.currentTime / video.duration) * 100);
                }}
              />
            ) : (
              <img
                className={mediaClassName}
                src={item.url}
                alt={item.alt_text}
                loading={eagerFirst && index === 0 ? "eager" : "lazy"}
              />
            )}
            {isActive && item.media_type === "video" ? (
              <>
                <button
                  type="button"
                  className="media-carousel-mute-toggle"
                  aria-label={isMuted(index) ? "Unmute video" : "Mute video"}
                  aria-pressed={!isMuted(index)}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    toggleMute(index);
                  }}
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" focusable="false">
                    <path d="M4 9v6h4l5 5V4L8 9H4z" fill="currentColor" />
                    {isMuted(index) ? (
                      <path
                        d="M16 8l5 8M21 8l-5 8"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        fill="none"
                      />
                    ) : (
                      <path
                        d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                        fill="none"
                      />
                    )}
                  </svg>
                </button>
                <div
                  className="media-carousel-progress"
                  role="slider"
                  tabIndex={0}
                  aria-label="Video progress"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(activeProgress)}
                  onClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    seekToClientX(index, event.clientX, event.currentTarget);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "ArrowRight") {
                      event.preventDefault();
                      event.stopPropagation();
                      seekBy(index, 5);
                    } else if (event.key === "ArrowLeft") {
                      event.preventDefault();
                      event.stopPropagation();
                      seekBy(index, -5);
                    }
                  }}
                >
                  <div className="media-carousel-progress-track">
                    <div className="media-carousel-progress-fill" style={{ width: `${activeProgress}%` }} />
                  </div>
                </div>
              </>
            ) : null}
          </div>
        );
      })}
      {showCaptions && activeItem?.caption ? (
        <p className="media-carousel-caption">{activeItem.caption}</p>
      ) : null}
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
