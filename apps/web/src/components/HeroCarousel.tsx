import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

type Slide =
  | { type: "image"; src: string; alt: string }
  | { type: "video"; src: string; alt: string };

const SLIDES: Slide[] = [
  { type: "image", src: "/media/ajisai-06-1.jpg", alt: "A bamboo whisk drizzling freshly whisked matcha into a mixing cup" },
  { type: "image", src: "/media/ajisai-08-1.jpg", alt: "Matcha being poured over milk and ice" },
  { type: "video", src: "/media/homepage-matcha-pour.mp4", alt: "Milk being poured over matcha and ice" },
  { type: "image", src: "/media/ajisai-05-1.jpg", alt: "Matcha syrup being whisked into milk for a latte" },
];

const ROTATE_MS = 5200;

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
      <p className="hero-credit">
        Photos &amp; video:{" "}
        <a href="https://www.nikonekomatcha.com/" target="_blank" rel="noreferrer">Niko Neko Matcha</a>
      </p>
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
