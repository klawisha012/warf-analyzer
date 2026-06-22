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
    <section class={`surface p-6 transition-colors duration-300 ${props.class ?? ""}`}>
      {(props.title || props.subtitle || props.trailing) && (
        <header class="flex items-center justify-between gap-4 mb-5 border-b border-line pb-3.5">
          <div class="min-w-0">
            {props.title && <h2 class="panel-title">{props.title}</h2>}
            {props.subtitle && <p class="panel-sub">{props.subtitle}</p>}
          </div>
          {props.trailing}
        </header>
      )}
      <div class="relative z-10 text-fg">{props.children}</div>
    </section>
  );
}
