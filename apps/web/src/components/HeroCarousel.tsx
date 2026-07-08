import { useEffect, useRef, useState } from "react";

type Slide =
  | { type: "image"; src: string; alt: string }
  | { type: "video"; src: string; alt: string };

const SLIDES: Slide[] = [
  { type: "image", src: "/media/homepage-sayaka-latte.jpg", alt: "A Sayaka matcha latte, freshly poured" },
  { type: "image", src: "/media/homepage-matcha-cup.jpg", alt: "A cup of whisked matcha" },
  { type: "video", src: "/media/homepage-matcha-pour.mp4", alt: "Milk being poured over matcha and ice" },
  { type: "image", src: "/media/homepage-matcha-used.jpg", alt: "A whisk resting after preparing matcha" },
];

const ROTATE_MS = 5200;

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/**
 * Crossfading hero background: three real photos plus the pour video, cycled
 * with a plain CSS opacity transition driven by a timer. Reduced-motion users
 * (and anyone who taps pause) get a single static photo instead — no
 * rotation, no autoplaying video.
 */
export function HeroCarousel() {
  const reducedMotion = usePrefersReducedMotion();
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  const isStatic = reducedMotion || paused;

  useEffect(() => {
    if (isStatic) return;
    const id = window.setInterval(() => setActive((index) => (index + 1) % SLIDES.length), ROTATE_MS);
    return () => window.clearInterval(id);
  }, [isStatic]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    try {
      if (!isStatic && SLIDES[active].type === "video") {
        video.currentTime = 0;
        video.play()?.catch(() => {});
      } else {
        video.pause();
      }
    } catch {
      // Media APIs are unimplemented in some test/SSR environments (jsdom);
      // the carousel is purely decorative, so a no-op here is safe.
    }
  }, [active, isStatic]);

  const visibleIndex = isStatic ? 0 : active;

  return (
    <div className="hero-carousel">
      {SLIDES.map((slide, index) => {
        const isActive = index === visibleIndex;
        if (isStatic && index !== 0) return null;
        return (
          <div className={`hero-slide${isActive ? " is-active" : ""}`} key={slide.src} aria-hidden={!isActive}>
            {slide.type === "video" ? (
              <video ref={videoRef} src={slide.src} muted loop playsInline autoPlay={isActive} aria-label={slide.alt} />
            ) : (
              <img src={slide.src} alt="" loading={index === 0 ? "eager" : "lazy"} />
            )}
          </div>
        );
      })}
      <div className="hero-scrim" />
      {!reducedMotion && (
        <button
          type="button"
          className="hero-pause"
          aria-pressed={paused}
          onClick={() => setPaused((value) => !value)}
        >
          {paused ? "Play slideshow" : "Pause slideshow"}
        </button>
      )}
    </div>
  );
}
