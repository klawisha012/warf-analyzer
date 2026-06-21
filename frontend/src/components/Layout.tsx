import { createSignal, For, Show, type JSX } from "solid-js";
import { A, useLocation } from "@solidjs/router";
import { createQuery, useQueryClient } from "@tanstack/solid-query";
import { fetchers, keys } from "../api/queries";
import { t, locale, setLocale } from "../i18n";

type LayoutProps = { children?: JSX.Element };

const reduceMotion =
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Icons (18×18 line glyphs) ---------------------------------------------------
const IcoDashboard = () => (
  <svg viewBox="0 0 24 24" fill="none"><path d="M4 13h6V4H4v9zm0 7h6v-5H4v5zm10 0h6V11h-6v9zm0-16v5h6V4h-6z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>
);
const IcoProfile = () => (
  <svg viewBox="0 0 24 24" fill="none"><path d="M12 12a4 4 0 100-8 4 4 0 000 8z" stroke="currentColor" stroke-width="1.6"/><path d="M4 21a8 8 0 0116 0" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
);
const IcoRiven = () => (
  <svg viewBox="0 0 24 24" fill="none"><path d="M12 2l2.4 5.6L20 9l-4.5 3.8L17 19l-5-3-5 3 1.5-6.2L4 9l5.6-1.4L12 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>
);
const IcoBell = () => (
  <svg viewBox="0 0 24 24" fill="none"><path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M13.7 21a2 2 0 01-3.4 0" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
);

const PROFILE_CHILDREN = [
  { href: "/inventory",   key: "nav.inventory"  },
  { href: "/prime-parts", key: "nav.primeParts" },
  { href: "/sets",        key: "nav.sets"       },
  { href: "/mods",        key: "nav.mods"       },
  { href: "/arcanes",     key: "nav.arcanes"    },
] as const;

export default function Layout(props: LayoutProps) {
  const loc = useLocation();
  const qc = useQueryClient();
  const [state, setState] = createSignal<"idle" | "pending" | "error">("idle");

  const childInActive = () => PROFILE_CHILDREN.some((c) => loc.pathname === c.href);
  const [open, setOpen] = createSignal(true);
  let childrenRef: HTMLDivElement | undefined;

  function toggleGroup() {
    const el = childrenRef;
    if (!el) { setOpen((o) => !o); return; }
    if (open()) {
      el.style.height = el.scrollHeight + "px";
      requestAnimationFrame(() => { el.style.height = "0px"; });
      setOpen(false);
    } else {
      setOpen(true);
      el.style.height = el.scrollHeight + "px";
      const onEnd = (e: TransitionEvent) => {
        if (e.propertyName === "height") {
          el.style.height = "auto";
          el.removeEventListener("transitionend", onEnd);
        }
      };
      el.addEventListener("transitionend", onEnd);
    }
  }

  const health = createQuery(() => ({
    queryKey: keys.healthz(),
    queryFn:  fetchers.healthz,
    refetchInterval: 30_000,
  }));
  const userName = () => health.data?.wfm_username ?? "Tenno";
  const initials = () => userName().slice(0, 2).toUpperCase();

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

  function magMove(e: MouseEvent & { currentTarget: HTMLButtonElement }) {
    if (reduceMotion) return;
    const b = e.currentTarget;
    const r = b.getBoundingClientRect();
    const clamp = (v: number) => Math.max(-8, Math.min(8, v));
    const dx = clamp((e.clientX - (r.left + r.width / 2)) * 0.3);
    const dy = clamp((e.clientY - (r.top + r.height / 2)) * 0.3);
    b.style.transform = `translate(${dx}px, ${dy}px)`;
  }
  function magLeave(e: MouseEvent & { currentTarget: HTMLButtonElement }) {
    e.currentTarget.style.transform = "translate(0, 0)";
  }

  return (
    <div class="app-shell">
      <aside class="sidebar" aria-label="Главная навигация">
        <div class="brand">
          <div class="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 2L21 7v10l-9 5-9-5V7l9-5z" stroke="#fff" stroke-width="1.6" stroke-linejoin="round" opacity="0.95"/>
              <path d="M12 2v20M3 7l9 5 9-5" stroke="#fff" stroke-width="1.4" stroke-linejoin="round" opacity="0.65"/>
            </svg>
          </div>
          <div class="brand-name">Aleca<span class="dot">Frame</span></div>
        </div>

        <nav class="nav">
          {/* Dashboard */}
          <A href="/" end class="nav-item" activeClass="active">
            <span class="nav-ico" aria-hidden="true"><IcoDashboard /></span>
            <span class="nav-label">{t("nav.dashboard")}</span>
          </A>

          {/* Profile group */}
          <div classList={{ "nav-group": true, open: open() }}>
            <div
              class="nav-item"
              classList={{ active: childInActive() && !open() }}
              role="button"
              tabindex="0"
              aria-expanded={open()}
              onClick={toggleGroup}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleGroup(); } }}
            >
              <span class="nav-ico" aria-hidden="true"><IcoProfile /></span>
              <span class="nav-label">{t("nav.profile")}</span>
              <svg class="chevron" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 6l6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="nav-children" ref={childrenRef} role="group" aria-label={t("nav.profile")}>
              <div class="nav-children-inner">
                <For each={PROFILE_CHILDREN}>
                  {(c) => (
                    <A href={c.href} class="nav-child" activeClass="active">{t(c.key)}</A>
                  )}
                </For>
              </div>
            </div>
          </div>

          <div class="nav-divider" role="separator" />

          {/* Riven Analyzer */}
          <A href="/rivens" class="nav-item riven" activeClass="active">
            <span class="nav-ico" aria-hidden="true"><IcoRiven /></span>
            <span class="nav-label">{t("nav.rivenAnalyzer")}</span>
          </A>

          {/* Notifications (Fissures) */}
          <A href="/fissures" class="nav-item" activeClass="active">
            <span class="nav-ico" aria-hidden="true"><IcoBell /></span>
            <span class="nav-label">{t("nav.notifications")}</span>
          </A>
        </nav>

        <div class="account" role="button" tabindex="0" title={userName()}>
          <div class="avatar" aria-hidden="true">{initials()}</div>
          <div class="account-meta">
            <div class="account-name">{userName()}</div>
            <div class="account-rep">
              <Show when={health.data?.ok} fallback={<span>{t("common.offline")}</span>}>
                <span>{t("common.online")}</span>
              </Show>
            </div>
          </div>
        </div>
      </aside>

      <div class="content-col">
        <div class="topbar">
          <div class="lang-toggle" role="group" aria-label={t("langToggle.label")}>
            <button type="button" classList={{ active: locale() === "ru" }} aria-pressed={locale() === "ru"} onClick={() => setLocale("ru")}>
              {t("langToggle.ru")}
            </button>
            <button type="button" classList={{ active: locale() === "en" }} aria-pressed={locale() === "en"} onClick={() => setLocale("en")}>
              {t("langToggle.en")}
            </button>
          </div>
          <button
            type="button"
            class="btn-primary"
            classList={{ spinning: state() === "pending" }}
            disabled={state() === "pending"}
            onClick={handleRefresh}
            onMouseMove={magMove}
            onMouseLeave={magLeave}
            aria-label={t("nav.refresh")}
          >
            <svg class="btn-ico" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M21 12a9 9 0 11-2.64-6.36M21 4v5h-5" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            {state() === "pending" ? t("nav.refreshing") : state() === "error" ? t("nav.refreshFailed") : t("nav.refresh")}
          </button>
        </div>
        <main class="content-main">{props.children}</main>
      </div>
    </div>
  );
}
