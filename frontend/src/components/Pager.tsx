import { Show } from "solid-js";

type PagerProps = {
  page: number;       // 0-based
  totalPages: number;
  total: number;
  onPage: (n: number) => void;
};

/** Prev / "page X of Y · N items" / Next control. Hidden when there's one page. */
export default function PagerControl(props: PagerProps) {
  return (
    <Show when={props.totalPages > 1}>
      <div class="flex items-center justify-between gap-3 pt-1 text-xs text-sub">
        <button
          type="button"
          class="btn-ghost px-3 py-1.5"
          disabled={props.page === 0}
          classList={{ "opacity-30 cursor-not-allowed": props.page === 0 }}
          onClick={() => props.onPage(props.page - 1)}
        >
          ←
        </button>
        <span class="num text-dim">
          {props.page + 1} / {props.totalPages} · {props.total}
        </span>
        <button
          type="button"
          class="btn-ghost px-3 py-1.5"
          disabled={props.page >= props.totalPages - 1}
          classList={{ "opacity-30 cursor-not-allowed": props.page >= props.totalPages - 1 }}
          onClick={() => props.onPage(props.page + 1)}
        >
          →
        </button>
      </div>
    </Show>
  );
}
