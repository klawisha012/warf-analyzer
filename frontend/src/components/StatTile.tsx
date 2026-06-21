import { Show, type JSX } from "solid-js";

type StatTileProps = {
  label: string;
  value: JSX.Element;
  icon?: JSX.Element;
  /** Small unit suffix shown after the value (e.g. "pl", "%"). */
  unit?: string;
  sub?: string;
  /** Tint the value mint (profit / positive) and the icon mint. */
  positive?: boolean;
};

export default function StatTile(props: StatTileProps) {
  return (
    <div class="tile">
      <div class="tile-label">
        <Show when={props.icon}>
          <span class="tile-ico" classList={{ mint: props.positive }} aria-hidden="true">{props.icon}</span>
        </Show>
        {props.label}
      </div>
      <div class="tile-value" classList={{ positive: props.positive }}>
        <span>{props.value}</span>
        <Show when={props.unit}><span class="unit">{props.unit}</span></Show>
      </div>
      <Show when={props.sub}><div class="tile-sub">{props.sub}</div></Show>
    </div>
  );
}
