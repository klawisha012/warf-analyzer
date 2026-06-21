import { Show, createSignal, createMemo } from "solid-js";
import { monogram } from "../lib/itemImages";

type ItemThumbProps = {
  src?: string | null;
  name: string;
  /** Square edge in px. Default 48. */
  size?: number;
  class?: string;
};

/**
 * Square item thumbnail. Renders the WFM image when available; on a missing
 * src OR a load error it degrades to a monogram tile that matches the design
 * system's `.item-ico` look, so the layout never shows a broken-image glyph.
 */
export default function ItemThumb(props: ItemThumbProps) {
  const [failed, setFailed] = createSignal(false);
  const showImg = createMemo(() => !!props.src && !failed());
  const px = () => props.size ?? 48;

  return (
    <div
      class={`item-ico shrink-0 overflow-hidden ${props.class ?? ""}`}
      style={{ width: `${px()}px`, height: `${px()}px` }}
      aria-hidden="true"
    >
      <Show when={showImg()} fallback={<span class="num">{monogram(props.name)}</span>}>
        <img
          src={props.src!}
          alt=""
          loading="lazy"
          decoding="async"
          class="w-full h-full object-contain p-1"
          onError={() => setFailed(true)}
        />
      </Show>
    </div>
  );
}
