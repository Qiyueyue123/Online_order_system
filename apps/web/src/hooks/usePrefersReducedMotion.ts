import { useEffect, useState } from "react";

/**
 * Tracks the user's prefers-reduced-motion setting live (not just at mount),
 * so carousels can drop crossfades/autoplay the moment it changes. Shared by
 * HeroCarousel and MediaCarousel rather than duplicated per component.
 */
export function usePrefersReducedMotion() {
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
