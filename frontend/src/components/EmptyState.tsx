import type { JSX } from "solid-js";

export default function EmptyState(props: {
  title: string;
  hint?: string;
  icon?: JSX.Element;
}) {
  return (
    <div class="text-center py-12 text-slate-400">
      {props.icon && <div class="mb-2 flex justify-center">{props.icon}</div>}
      <div class="text-slate-200 font-medium">{props.title}</div>
      {props.hint && <div class="text-sm mt-1">{props.hint}</div>}
    </div>
  );
}
