import { Show, type JSX } from "solid-js";

type PageHeaderProps = {
  title: string;
  /** Small uppercase-ish status line above the title. */
  eyebrow?: JSX.Element;
  /** Render the mint pulse dot before the eyebrow text. */
  pulse?: boolean;
  /** Right-aligned actions (filters, controls). */
  actions?: JSX.Element;
};

export default function PageHeader(props: PageHeaderProps) {
  return (
    <header class="page-head">
      <div class="titles">
        <Show when={props.eyebrow}>
          <div class="eyebrow">
            <Show when={props.pulse}>
              <span class="pulse" />
            </Show>
            {props.eyebrow}
          </div>
        </Show>
        <h1 class="page-title">{props.title}</h1>
      </div>
      <Show when={props.actions}>
        <div class="head-actions">{props.actions}</div>
      </Show>
    </header>
  );
}
