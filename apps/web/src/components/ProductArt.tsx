import type { ReactElement } from "react";

type ArtKind = "tin" | "whisk" | "bowl" | "scoop" | "sifter" | "leaf";

/**
 * Maps a product to one of a small set of hand-tuned line-art illustrations.
 * Matching is keyword-based against slug/category/name so any future seed
 * product lands on a sensible icon instead of a blank block.
 */
function resolveArtKind(input: { slug: string; category?: string | null; name?: string | null }): ArtKind {
  const hay = `${input.slug} ${input.category ?? ""} ${input.name ?? ""}`.toLowerCase();
  if (/whisk|chasen/.test(hay)) return "whisk";
  if (/sift|sieve|furui|strain/.test(hay)) return "sifter";
  if (/scoop|chashaku|spoon/.test(hay)) return "scoop";
  if (/sampler|pouch/.test(hay)) return "tin";
  if (/bowl|chawan/.test(hay)) return "bowl";
  if (/tin|matcha|tea|ceremonial|uji|cultivar|blend/.test(hay)) return "tin";
  return "leaf";
}

function TinArt() {
  return (
    <svg viewBox="0 0 200 240" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="100" cy="56" rx="34" ry="10" />
      <ellipse cx="100" cy="68" rx="44" ry="13" />
      <path d="M56 68 L56 178 Q56 196 100 196 Q144 196 144 178 L144 68" />
      <line x1="72" y1="104" x2="128" y2="104" />
      <line x1="72" y1="140" x2="128" y2="140" />
      <path d="M84 118 Q100 112 116 118" opacity=".6" />
    </svg>
  );
}

function WhiskArt() {
  return (
    <svg viewBox="0 0 200 240" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {/* bamboo handle */}
      <line x1="87" y1="156" x2="87" y2="206" />
      <line x1="113" y1="156" x2="113" y2="206" />
      <ellipse cx="100" cy="206" rx="13" ry="5" />
      {/* tied string collar */}
      <path d="M84 148 Q100 154 116 148" />
      <path d="M84 142 Q100 148 116 142" />
      <path d="M84 142 L84 148 M116 142 L116 148" />
      {/* outer tines rising from the collar, curving inward at the top */}
      <path d="M85 142 C 66 112 64 72 92 42 Q97 38 99 44" />
      <path d="M115 142 C 134 112 136 72 108 42 Q103 38 101 44" />
      {/* inner tines */}
      <path d="M91 142 C 78 110 79 74 96 46" opacity=".75" />
      <path d="M109 142 C 122 110 121 74 104 46" opacity=".75" />
      <path d="M96 142 C 90 110 92 76 99 50" opacity=".55" />
      <path d="M104 142 C 110 110 108 76 101 50" opacity=".55" />
      <path d="M100 142 L100 54" opacity=".4" />
    </svg>
  );
}

function BowlArt() {
  return (
    <svg viewBox="0 0 200 240" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="100" cy="108" rx="62" ry="15" />
      <path d="M38 108 Q46 172 100 180 Q154 172 162 108" />
      <line x1="82" y1="196" x2="118" y2="196" />
      <path d="M74 122 Q100 132 126 122" opacity=".55" />
      <path d="M70 108 Q100 98 130 108" opacity=".4" />
    </svg>
  );
}

function ScoopArt() {
  return (
    <svg viewBox="0 0 200 240" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M118 34 C 148 66 150 100 132 132 C 118 156 96 168 78 176" />
      <path d="M78 176 Q56 182 58 200 Q62 214 82 210 Q100 204 96 186 Q92 178 78 176 Z" />
      <path d="M112 46 C 132 74 134 98 122 122" opacity=".5" />
    </svg>
  );
}

function SifterArt() {
  return (
    <svg viewBox="0 0 200 240" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="94" cy="100" r="54" />
      <path d="M148 100 Q176 110 182 138" />
      <line x1="62" y1="76" x2="126" y2="124" opacity=".5" />
      <line x1="126" y1="76" x2="62" y2="124" opacity=".5" />
      <line x1="94" y1="52" x2="94" y2="148" opacity=".4" />
      <line x1="52" y1="100" x2="136" y2="100" opacity=".4" />
      <circle cx="94" cy="100" r="54" opacity=".9" />
    </svg>
  );
}

function LeafArt() {
  return (
    <svg viewBox="0 0 200 240" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M100 40 C 150 66 156 128 100 200 C 44 128 50 66 100 40 Z" />
      <line x1="100" y1="52" x2="100" y2="188" />
      <path d="M100 84 Q120 92 130 108" opacity=".6" />
      <path d="M100 84 Q80 92 70 108" opacity=".6" />
      <path d="M100 122 Q124 130 136 148" opacity=".5" />
      <path d="M100 122 Q76 130 64 148" opacity=".5" />
    </svg>
  );
}

const ART: Record<ArtKind, () => ReactElement> = {
  tin: TinArt,
  whisk: WhiskArt,
  bowl: BowlArt,
  scoop: ScoopArt,
  sifter: SifterArt,
  leaf: LeafArt,
};

export function ProductArt({
  slug,
  category,
  name,
  tone = 0,
}: {
  slug: string;
  category?: string | null;
  name?: string | null;
  tone?: number;
}) {
  const kind = resolveArtKind({ slug, category, name });
  const Art = ART[kind];
  return (
    <div className={`product-art-panel tone-${tone % 4}`} aria-hidden="true">
      <Art />
    </div>
  );
}
