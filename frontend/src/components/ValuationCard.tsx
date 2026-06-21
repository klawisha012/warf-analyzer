import { For, Show } from "solid-js";
import ItemThumb from "./ItemThumb";

type Tone = "fg" | "sub" | "mint" | "cyan";
const TONE: Record<Tone, string> = {
  fg: "text-fg",
  sub: "text-sub",
  mint: "text-mint",
  cyan: "text-cyan",
};

export type Stat = { label: string; value: string; tone?: Tone };

type ValuationCardProps = {
  name: string;
  slug: string | null;
  thumb?: string | null;
  /** Mod / arcane max rank → small "R{n}" badge. */
  rank?: number | null;
  stats: Stat[];
  /** Emphasized headline value (estimated value), tinted mint. */
  primary?: { label: string; value: string };
};

/**
 * Image-led item card. Replaces the dense valuation tables: thumbnail + name,
 * a compact stat row, and the estimated value as the headline number.
 */
export default function ValuationCard(props: ValuationCardProps) {
  return (
    <article class="surface p-4 flex items-center gap-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-line-strong">
      <ItemThumb src={props.thumb} name={props.name} size={52} />

      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <Show
            when={props.slug}
            fallback={<h3 class="text-fg font-semibold text-[14px] truncate">{props.name}</h3>}
          >
            <a
              href={`https://warframe.market/items/${props.slug}`}
              target="_blank"
              rel="noopener noreferrer"
              class="text-fg font-semibold text-[14px] truncate hover:text-brand-soft transition-colors"
            >
              {props.name}
            </a>
          </Show>
          <Show when={props.rank != null}>
            <span class="text-[9px] text-dim num px-1.5 py-0.5 rounded bg-surface2 border border-line uppercase tracking-widest shrink-0">
              R{props.rank}
            </span>
          </Show>
        </div>

        <div class="mt-2 flex flex-wrap gap-x-5 gap-y-1">
          <For each={props.stats}>
            {(s) => (
              <div class="flex flex-col">
                <span class="text-[10px] text-dim uppercase tracking-wider">{s.label}</span>
                <span class={`num text-[13px] font-semibold ${TONE[s.tone ?? "sub"]}`}>{s.value}</span>
              </div>
            )}
          </For>
        </div>
      </div>

      <Show when={props.primary}>
        <div class="text-right shrink-0 pl-2">
          <div class="num text-[20px] font-bold text-mint leading-none">{props.primary!.value}</div>
          <div class="text-[10px] text-dim uppercase tracking-wider mt-1.5">{props.primary!.label}</div>
        </div>
      </Show>
    </article>
  );
}
