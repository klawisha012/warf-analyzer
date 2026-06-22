// i18n entry. Default locale: ru. Toggle via setLocale() — persisted in localStorage.
//
// Usage:
//   import { t, locale, setLocale } from "../i18n";
//   <span>{t("nav.dashboard")}</span>
//   <span>{t("primeParts.rowsSummary", { count: 5, total: "120p" })}</span>
//
// @solid-primitives/i18n's `chainedTranslator` accepts a flattened dict; we
// flatten our nested ru/en at module load.
import * as i18n from "@solid-primitives/i18n";
import { createSignal, createMemo } from "solid-js";

import { ru } from "./dict/ru";
import { en } from "./dict/en";

export type Locale = "ru" | "en";

const STORAGE_KEY = "alecaframe.locale";

function readStoredLocale(): Locale {
  if (typeof localStorage === "undefined") return "ru";
  const v = localStorage.getItem(STORAGE_KEY);
  return v === "en" ? "en" : "ru";
}

const dicts = { ru, en } as const;

const [_locale, _setLocale] = createSignal<Locale>(readStoredLocale());

export const locale = _locale;

export function setLocale(next: Locale): void {
  _setLocale(next);
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore (SSR / private mode) */
  }
}

// Hand-rolled flatten — the lib's `flatten` has strict template-literal typing
// that fights with our 3-deep nested dicts (inventory.slot.warframe, etc.).
// Recursing manually keeps the runtime behavior identical and the types simple.
function flattenDict(
  obj: unknown,
  prefix = "",
  out: Record<string, string> = {},
): Record<string, string> {
  if (obj && typeof obj === "object") {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === "object") {
        flattenDict(v, key, out);
      } else if (typeof v === "string") {
        out[key] = v;
      }
    }
  }
  return out;
}

const flatDict = createMemo(() => flattenDict(dicts[_locale()]));
// eslint-disable-next-line solid/reactivity -- translator() from @solid-primitives/i18n accepts an Accessor and tracks it internally
const _t = i18n.translator(flatDict, i18n.resolveTemplate);

export function t(key: string, params?: Record<string, string | number>): string {
  const out = _t(key as never, params as never);
  return typeof out === "string" ? out : key;
}
