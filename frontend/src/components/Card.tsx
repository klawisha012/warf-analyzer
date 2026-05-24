import type { JSX } from "solid-js";

type CardProps = {
  title?: string;
  subtitle?: string;
  trailing?: JSX.Element;
  children: JSX.Element;
  class?: string;
};

export default function Card(props: CardProps) {
  return (
    <section
      class={`rounded-2xl bg-slate-900 border border-slate-800 p-4 ${props.class ?? ""}`}
    >
      {(props.title || props.subtitle || props.trailing) && (
        <header class="flex items-center justify-between gap-4 mb-3">
          <div>
            {props.title && <h2 class="text-lg font-semibold text-slate-100">{props.title}</h2>}
            {props.subtitle && <p class="text-sm text-slate-400">{props.subtitle}</p>}
          </div>
          {props.trailing}
        </header>
      )}
      {props.children}
    </section>
  );
}
