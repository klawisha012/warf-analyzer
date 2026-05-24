import type { JSX } from "solid-js";
import { A, useLocation } from "@solidjs/router";

type LayoutProps = { children?: JSX.Element };

const NAV = [
  { href: "/",            label: "Dashboard"   },
  { href: "/inventory",   label: "Inventory"   },
  { href: "/prime-parts", label: "Prime Parts" },
  { href: "/sets",        label: "Sets"        },
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
              {item.label}
            </A>
          ))}
        </nav>
      </header>
      <main class="max-w-6xl mx-auto px-6 py-6">{props.children}</main>
    </div>
  );
}
