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
      class={`rounded-3xl glass-panel glass-panel-hover p-6 shadow-[0_12px_40px_rgba(0,0,0,0.25)] transition-all duration-500 ${props.class ?? ""}`}
    >
      {(props.title || props.subtitle || props.trailing) && (
        <header class="flex items-center justify-between gap-4 mb-5 border-b border-white/[0.02] pb-3">
          <div>
            {props.title && (
              <h2 class="text-base font-semibold tracking-tight text-slate-200">
                {props.title}
              </h2>
            )}
            {props.subtitle && (
              <p class="text-xs text-slate-500 mt-0.5">
                {props.subtitle}
              </p>
            )}
          </div>
          {props.trailing}
        </header>
      )}
      <div class="relative z-10 text-slate-200">
        {props.children}
      </div>
    </section>
  );
}
