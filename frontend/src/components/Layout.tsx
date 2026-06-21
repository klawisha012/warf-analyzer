import { createSignal, Show, type JSX } from "solid-js";
import { A, useLocation } from "@solidjs/router";
import { useQueryClient } from "@tanstack/solid-query";
import { fetchers } from "../api/queries";
import { t, locale, setLocale } from "../i18n";

type LayoutProps = { children?: JSX.Element };

const NAV = [
  { href: "/",            key: "nav.dashboard"  },
  { href: "/inventory",   key: "nav.inventory"  },
  { href: "/prime-parts", key: "nav.primeParts" },
  { href: "/mods",        key: "nav.mods"       },
  { href: "/arcanes",     key: "nav.arcanes"    },
  { href: "/sets",        key: "nav.sets"       },
  { href: "/rivens",      key: "nav.rivens"     },
  { href: "/fissures",    key: "nav.fissures"   },
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
    <div class="min-h-screen text-slate-100 relative pb-12">
      <header class="sticky top-0 z-50 bg-slate-950/40 backdrop-blur-2xl border-b border-white/[0.04] shadow-[0_4px_30px_rgba(0,0,0,0.2)]">
        <nav class="max-w-6xl mx-auto px-6 py-4 flex items-center gap-2">
          {/* Futuristic High-Tech Logo & Emblem */}
          <div class="flex items-center gap-3 mr-6">
            <div class="relative w-8 h-8 flex items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 border border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
              <svg class="w-4.5 h-4.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m0-12.728l.707.707m12.728 12.728l.707.707M12 8a4 4 0 100 8 4 4 0 000-8z"></path>
              </svg>
              <span class="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
              <span class="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400"></span>
            </div>
            <span class="font-bold tracking-tight text-lg text-slate-100 flex items-center gap-1.5">
              Aleca<span class="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-300">Frame</span>
            </span>
          </div>

          {/* Navigation Links */}
          <div class="flex items-center gap-1.5">
            {NAV.map((item) => (
              <A
                href={item.href}
                end={item.href === "/"}
                class="px-4 py-1.5 rounded-xl text-sm font-medium transition-all duration-300 border border-transparent"
                classList={{
                  "bg-gradient-to-r from-emerald-500/10 to-teal-500/10 text-emerald-300 border-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.04)]": loc.pathname === item.href,
                  "text-slate-400 hover:text-slate-100 hover:bg-white/[0.02] hover:border-white/[0.04]": loc.pathname !== item.href,
                }}
              >
                {t(item.key)}
              </A>
            ))}
          </div>

          {/* Refresh Control */}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={state() === "pending"}
            class="ml-auto flex items-center gap-2 px-4 py-1.5 rounded-xl text-sm border font-medium transition-all duration-300 disabled:cursor-wait"
            classList={{
              "border-slate-800 bg-slate-900/30 text-slate-300 hover:text-slate-100 hover:bg-slate-900/70 hover:border-slate-700/50 shadow-sm": state() === "idle",
              "border-emerald-900/30 bg-emerald-950/10 text-emerald-400 font-semibold shadow-[0_0_15px_rgba(16,185,129,0.05)]": state() === "pending",
              "border-red-900/30 bg-red-950/10 text-red-400 shadow-[0_0_15px_rgba(239,68,68,0.05)]": state() === "error",
            }}
            aria-label={t("nav.refresh")}
          >
            <Show when={state() === "pending"}>
              <svg class="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3m0 0l3 3m-3-3v12"></path>
              </svg>
            </Show>
            <span>
              {state() === "pending"
                ? t("nav.refreshing")
                : state() === "error"
                  ? t("nav.refreshFailed")
                  : t("nav.refresh")}
            </span>
          </button>

          {/* Premium Language Toggler */}
          <div
            class="ml-3 flex items-center gap-0.5 rounded-xl border border-white/[0.04] bg-slate-950/30 p-0.5 shadow-inner"
            role="group"
            aria-label={t("langToggle.label")}
          >
            <button
              type="button"
              onClick={() => setLocale("ru")}
              class="px-3 py-1 text-xs rounded-lg font-medium transition-all duration-300"
              classList={{
                "bg-slate-900/80 text-emerald-400 shadow-sm border border-emerald-500/20": locale() === "ru",
                "text-slate-400 hover:text-slate-200": locale() !== "ru",
              }}
            >
              {t("langToggle.ru")}
            </button>
            <button
              type="button"
              onClick={() => setLocale("en")}
              class="px-3 py-1 text-xs rounded-lg font-medium transition-all duration-300"
              classList={{
                "bg-slate-900/80 text-emerald-400 shadow-sm border border-emerald-500/20": locale() === "en",
                "text-slate-400 hover:text-slate-200": locale() !== "en",
              }}
            >
              {t("langToggle.en")}
            </button>
          </div>
        </nav>
      </header>
      <main class="max-w-6xl mx-auto px-6 py-8 relative z-10">{props.children}</main>
    </div>
  );
}
