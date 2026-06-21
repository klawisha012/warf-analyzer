import type { JSX } from "solid-js";

type Variant = "neutral" | "good" | "warn" | "bad" | "vaulted" | "info";

// Map the legacy variant names onto the Aurora chip palette:
// good → mint (online), info/vaulted → indigo (brand), warn → amber, bad → rose.
const VARIANT: Record<Variant, string> = {
  neutral: "chip",
  good:    "chip online",
  warn:    "chip warn",
  bad:     "chip bad",
  vaulted: "chip brand",
  info:    "chip brand",
};

export default function Badge(props: { variant?: Variant; children: JSX.Element }) {
  return <span class={VARIANT[props.variant ?? "neutral"]}>{props.children}</span>;
}
