import { createSignal, type JSX } from "solid-js";
import { A, useLocation } from "@solidjs/router";
import { useQueryClient } from "@tanstack/solid-query";
import { fetchers } from "../api/queries";
import { t, locale, setLocale } from "../i18n";

type LayoutProps = { children?: JSX.Element };

const NAV = [
  { href: "/",            key: "nav.dashboard"  },
  { href: "/inventory",   key: "nav.inventory"  },
  { href: "/prime-parts", key: "nav.primeParts" },
  { href: "/sets",        key: "nav.sets"       },
  { href: "/rivens",      key: "nav.rivens"     },
] as const;

export default function Layout(props: LayoutProps) {
  const loc = useLocation();
  const qc = useQueryClient();
  const [state, setState] = createSignal<"idle" | "pending" | "error">("idle");

  async function handleRefresh() {
    if (state() === "pending") return;
    setState("pending");
    try {
      await fetchers.refresh();
      // Every /me/* query reads bridge.lastdata() — invalidate them all so
      // they refetch the freshly-decrypted inventory snapshot.
      await qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === "me" });
      setState("idle");
    } catch (e) {
      console.warn("refresh failed:", e);
      setState("error");
      setTimeout(() => setState("idle"), 3000);
    }
  }

  return (
    <div class="min-h-screen text-slate-100 bg-slate-950">
      <header class="sticky top-0 z-10 bg-slate-950/80 backdrop-blur border-b border-slate-800">
        <nav class="max-w-6xl mx-auto px-6 py-3 flex items-center gap-1">
          <span class="font-semibold text-slate-200 mr-4">AlecaFrame</span>
          {NAV.map((item) => (
            <A
              href={item.href}
              end={item.href === "/"}
              class="px-3 py-1.5 rounded-lg text-sm transition-colors"
              classList={{
                "bg-slate-800 text-slate-100": loc.pathname === item.href,
                "text-slate-400 hover:text-slate-100 hover:bg-slate-900":
                  loc.pathname !== item.href,
              }}
            >
              {t(item.key)}
            </A>
          ))}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={state() === "pending"}
            class="ml-auto px-3 py-1.5 rounded-lg text-sm border transition-colors disabled:cursor-wait"
            classList={{
              "border-slate-800 text-slate-300 hover:text-slate-100 hover:bg-slate-900": state() === "idle",
              "border-slate-700 text-slate-500": state() === "pending",
              "border-red-900 text-red-400": state() === "error",
            }}
            aria-label={t("nav.refresh")}
          >
            {state() === "pending"
              ? t("nav.refreshing")
              : state() === "error"
                ? t("nav.refreshFailed")
                : t("nav.refresh")}
          </button>
          <div
            class="ml-2 flex items-center gap-0.5 rounded-md border border-slate-800 p-0.5"
            role="group"
            aria-label={t("langToggle.label")}
          >
            <button
              type="button"
              onClick={() => setLocale("ru")}
              class="px-2 py-0.5 text-xs rounded font-medium"
              classList={{
                "bg-slate-800 text-slate-100": locale() === "ru",
                "text-slate-400 hover:text-slate-200": locale() !== "ru",
              }}
            >
              {t("langToggle.ru")}
            </button>
            <button
              type="button"
              onClick={() => setLocale("en")}
              class="px-2 py-0.5 text-xs rounded font-medium"
              classList={{
                "bg-slate-800 text-slate-100": locale() === "en",
                "text-slate-400 hover:text-slate-200": locale() !== "en",
              }}
            >
              {t("langToggle.en")}
            </button>
          </div>
        </nav>
      </header>
      <main class="max-w-6xl mx-auto px-6 py-6">{props.children}</main>
    </div>
  );
}
