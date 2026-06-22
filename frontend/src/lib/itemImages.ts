// Item thumbnails. WFM exposes a slug → thumb path in the /wfm/items catalogue
// (relative, e.g. "/items/images/thumbs/loki_prime_set.png"). We fetch that
// catalogue once (cached 24h + persisted to localStorage like every other
// query), build a slug → absolute-URL map, and hand callers a plain accessor.
// Missing slugs / offline → null; <ItemThumb> falls back to a monogram tile.
import { createQuery } from "@tanstack/solid-query";
import { createMemo } from "solid-js";
import { fetchers, keys } from "../api/queries";

const WFM_ASSET_BASE = "https://warframe.market/static/assets";

/** Turn a WFM relative asset path into an absolute URL. Passes through absolute URLs. */
export function wfmAsset(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//.test(path)) return path;
  return `${WFM_ASSET_BASE}/${path.replace(/^\/+/, "")}`;
}

// Fallback art via the warframestat CDN, keyed by the DE imageName the backend
// now ships on each item. Covers items WFM has no thumbnail for (whole
// warframes etc.). 404s degrade to the monogram tile in <ItemThumb>.
const WARFRAMESTAT_IMG_BASE = "https://cdn.warframestat.us/img";
export function warframestatImg(imageName: string | null | undefined): string | null {
  if (!imageName) return null;
  if (/^https?:\/\//.test(imageName)) return imageName;
  return `${WARFRAMESTAT_IMG_BASE}/${imageName.replace(/^\/+/, "")}`;
}

/**
 * Reactive slug → thumbnail-URL accessor. The underlying /wfm/items query is
 * deduped by TanStack Query, so calling this hook from many components costs
 * exactly one network request.
 */
export function useItemThumbs(): (slug: string | null | undefined) => string | null {
  const q = createQuery(() => ({
    queryKey: keys.wfmItems(),
    queryFn: fetchers.wfmItems,
    staleTime: 24 * 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  }));
  const map = createMemo(() => {
    const m = new Map<string, string>();
    for (const it of q.data?.items ?? []) {
      const url = wfmAsset(it.thumb_url);
      if (url) m.set(it.slug, url);
    }
    return m;
  });
  // eslint-disable-next-line solid/reactivity -- returned closure is always called inside JSX or a tracked scope by callers
  return (slug) => (slug ? (map().get(slug) ?? null) : null);
}

/** First letters of up to two significant words → monogram fallback (e.g. "Loki Prime" → "LP"). */
export function monogram(name: string): string {
  const words = name
    .replace(/\bprime\b/i, "")
    .split(/\s+/)
    .filter(Boolean);
  const pick = words.length >= 2 ? words.slice(0, 2) : [name];
  return (
    pick
      .map((w) => w[0]?.toUpperCase() ?? "")
      .join("")
      .slice(0, 2) || "?"
  );
}
