import type { JSX } from "solid-js";

export default function EmptyState(props: { title: string; hint?: string; icon?: JSX.Element }) {
  return (
    <div class="text-center py-14 text-sub">
      {props.icon && <div class="mb-3 flex justify-center text-dim">{props.icon}</div>}
      <div class="text-fg font-semibold">{props.title}</div>
      {props.hint && <div class="text-sm text-dim mt-1.5">{props.hint}</div>}
    </div>
  );
}
