import type { JSX } from "solid-js";
import { A, useLocation } from "@solidjs/router";
import { t, locale, setLocale } from "../i18n";

type LayoutProps = { children?: JSX.Element };

const NAV = [
  { href: "/",            key: "nav.dashboard"  },
  { href: "/inventory",   key: "nav.inventory"  },
  { href: "/prime-parts", key: "nav.primeParts" },
  { href: "/sets",        key: "nav.sets"       },
] as const;

export default function Layout(props: LayoutProps) {
  const loc = useLocation();
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
          <div
            class="ml-auto flex items-center gap-0.5 rounded-md border border-slate-800 p-0.5"
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
