import { Show, createSignal, createMemo } from "solid-js";
import { monogram } from "../lib/itemImages";

type ItemThumbProps = {
  src?: string | null;
  /** Tried if `src` is missing or fails to load (e.g. warframestat art). */
  fallback?: string | null;
  name: string;
  /** Square edge in px. Default 48. */
  size?: number;
  class?: string;
};

/**
 * Square item thumbnail. Tries `src`, then `fallback`, then degrades to a
 * monogram tile matching the design's `.item-ico` look, so the layout never
 * shows a broken-image glyph.
 */
export default function ItemThumb(props: ItemThumbProps) {
  const sources = createMemo(() => [props.src, props.fallback].filter(Boolean) as string[]);
  const [idx, setIdx] = createSignal(0);
  // Reset to the first source whenever the candidate list changes identity.
  const current = createMemo(() => {
    void sources();
    return sources()[idx()] ?? null;
  });
  const px = () => props.size ?? 48;

  return (
    <div
      class={`item-ico shrink-0 overflow-hidden ${props.class ?? ""}`}
      style={{ width: `${px()}px`, height: `${px()}px` }}
      aria-hidden="true"
    >
      <Show when={current()} fallback={<span class="num">{monogram(props.name)}</span>}>
        <img
          src={current()!}
          alt=""
          loading="lazy"
          decoding="async"
          class="w-full h-full object-contain p-1"
          onError={() => setIdx((i) => i + 1)}
        />
      </Show>
    </div>
  );
}
