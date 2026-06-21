import { For, Show, createSignal } from "solid-js";
import { createQuery, useQueryClient } from "@tanstack/solid-query";
import Card from "../components/Card";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import { fetchers, keys } from "../api/queries";
import { t } from "../i18n";

// tri-state <select> value -> nullable bool: "" any, "yes" true, "no" false.
function triToBool(v: string): boolean | null {
  if (v === "yes") return true;
  if (v === "no") return false;
  return null;
}

function fmtEta(sec: number | null | undefined): string {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export default function Fissures() {
  const qc = useQueryClient();

  const live = createQuery(() => ({
    queryKey: keys.fissuresLive(),
    queryFn: fetchers.fissuresLive,
    refetchInterval: 30_000,
  }));
  const meta = createQuery(() => ({
    queryKey: keys.fissuresMeta(),
    queryFn: fetchers.fissuresMeta,
    staleTime: 60 * 60 * 1000,
  }));
  const subs = createQuery(() => ({
    queryKey: keys.fissuresSubs(),
    queryFn: fetchers.fissuresSubsList,
    refetchInterval: 30_000,
  }));
  const chats = createQuery(() => ({
    queryKey: keys.fissuresChats(),
    queryFn: fetchers.fissuresChats,
    refetchInterval: 30_000,
  }));

  const [era, setEra] = createSignal("");
  const [mission, setMission] = createSignal("");
  const [planet, setPlanet] = createSignal("");
  const [node, setNode] = createSignal("");
  const [hard, setHard] = createSignal("");
  const [storm, setStorm] = createSignal("");

  // Node suggestions: the chosen planet's full star-chart list (so you can pick
  // a node that has no live fissure yet); with no planet, the currently-live nodes.
  const nodeOptions = () => {
    const p = planet();
    const byPlanet = meta.data?.nodes_by_planet ?? {};
    return p && byPlanet[p]?.length ? byPlanet[p] : (meta.data?.nodes ?? []);
  };

  // Any non-empty filter is an active constraint.
  const hasFilters = () =>
    !!(era() || mission() || planet() || node().trim() || hard() || storm());

  // The same controls that build a subscription also narrow the live list;
  // an empty value means "no constraint" for that field.
  const filteredLive = () => {
    const items = live.data?.items ?? [];
    const e = era(), m = mission(), p = planet();
    const n = node().trim().toLowerCase();
    const h = triToBool(hard()), s = triToBool(storm());
    return items.filter((f) =>
      (!e || f.era === e) &&
      (!m || f.mission_type === m) &&
      (!p || f.planet === p) &&
      (!n || (f.node ?? "").toLowerCase() === n) &&
      (h === null || f.is_hard === h) &&
      (s === null || f.is_storm === s),
    );
  };

  function clearFilters() {
    setEra(""); setMission(""); setPlanet(""); setNode(""); setHard(""); setStorm("");
  }

  async function addSub() {
    await fetchers.fissuresSubAdd({
      era: era() || null,
      mission_type: mission() || null,
      planet: planet() || null,
      node: node().trim() || null,
      is_hard: triToBool(hard()),
      is_storm: triToBool(storm()),
    });
    setEra(""); setMission(""); setPlanet(""); setNode(""); setHard(""); setStorm("");
    await qc.invalidateQueries({ queryKey: keys.fissuresSubs() });
  }

  async function removeSub(id: number) {
    await fetchers.fissuresSubRemove(id);
    await qc.invalidateQueries({ queryKey: keys.fissuresSubs() });
  }

  async function sendTest() {
    await fetchers.fissuresTest();
    await qc.invalidateQueries({ queryKey: keys.fissuresChats() });
  }

  return (
    <div class="space-y-6">
      <PageHeader title={t("fissures.title")} pulse eyebrow={<span>{t("fissures.live")}</span>} />

      <div class="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4">
        <div class="space-y-4">
          <Card title={t("fissures.subscriptions")}>
            <div class="space-y-2.5">
              <label class="block text-xs text-sub">{t("fissures.era")}</label>
              <select value={era()} onChange={(e) => setEra(e.currentTarget.value)} class="field">
                <option value="">{t("fissures.any")}</option>
                <For each={meta.data?.eras ?? []}>{(x) => <option value={x}>{x}</option>}</For>
              </select>

              <label class="block text-xs text-sub">{t("fissures.mission")}</label>
              <select value={mission()} onChange={(e) => setMission(e.currentTarget.value)} class="field">
                <option value="">{t("fissures.any")}</option>
                <For each={meta.data?.mission_types ?? []}>{(x) => <option value={x}>{x}</option>}</For>
              </select>

              <label class="block text-xs text-sub">{t("fissures.planet")}</label>
              <select value={planet()} onChange={(e) => setPlanet(e.currentTarget.value)} class="field">
                <option value="">{t("fissures.any")}</option>
                <For each={meta.data?.planets ?? []}>{(x) => <option value={x}>{x}</option>}</For>
              </select>

              <label class="block text-xs text-sub">{t("fissures.node")}</label>
              <input
                value={node()}
                onInput={(e) => setNode(e.currentTarget.value)}
                list="fissure-nodes"
                placeholder={t("fissures.nodePlaceholder")}
                class="field"
              />
              <datalist id="fissure-nodes">
                <For each={nodeOptions()}>{(x) => <option value={x} />}</For>
              </datalist>

              <label class="block text-xs text-sub">{t("fissures.steelPath")}</label>
              <select value={hard()} onChange={(e) => setHard(e.currentTarget.value)} class="field">
                <option value="">{t("fissures.any")}</option>
                <option value="yes">{t("fissures.yes")}</option>
                <option value="no">{t("fissures.no")}</option>
              </select>

              <label class="block text-xs text-sub">{t("fissures.voidStorm")}</label>
              <select value={storm()} onChange={(e) => setStorm(e.currentTarget.value)} class="field">
                <option value="">{t("fissures.any")}</option>
                <option value="yes">{t("fissures.yes")}</option>
                <option value="no">{t("fissures.no")}</option>
              </select>

              <button type="button" onClick={addSub} class="btn-primary w-full justify-center mt-1">
                {t("fissures.addSub")}
              </button>
            </div>

            <div class="mt-4">
              <Show
                when={(subs.data?.items ?? []).length > 0}
                fallback={<div class="text-sm text-dim">{t("fissures.subsEmpty")}</div>}
              >
                <ul class="space-y-1.5">
                  <For each={subs.data?.items ?? []}>
                    {(s) => (
                      <li class="flex items-center justify-between gap-2 px-3 py-2 rounded-[10px] bg-surface2 border border-line">
                        <span class="flex flex-wrap gap-1.5 items-center">
                          <Badge variant="info">{s.era ?? t("fissures.any")}</Badge>
                          <Badge>{s.mission_type ?? t("fissures.any")}</Badge>
                          <Show when={s.planet}><Badge variant="info">{s.planet}</Badge></Show>
                          <Show when={s.node}><Badge>{s.node}</Badge></Show>
                          <Show when={s.is_hard === true}><Badge variant="warn">SP</Badge></Show>
                          <Show when={s.is_storm === true}><Badge variant="vaulted">Storm</Badge></Show>
                        </span>
                        <button type="button" onClick={() => removeSub(s.id)} class="text-dim hover:text-rose-400 px-1 transition-colors">×</button>
                      </li>
                    )}
                  </For>
                </ul>
              </Show>
            </div>
          </Card>

          <Card title={t("fissures.telegram")}>
            <Show
              when={chats.data?.bot_enabled}
              fallback={<div class="text-sm text-amber-300">{t("fissures.botDisabled")}</div>}
            >
              <p class="text-sm text-sub">{t("fissures.startHint")}</p>
              <Show when={chats.data?.bot_username}>
                <a
                  href={`https://t.me/${chats.data!.bot_username}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="btn-ghost mt-3 inline-flex"
                >
                  @{chats.data!.bot_username} ↗
                </a>
              </Show>
              <div class="mt-3">
                <Show
                  when={(chats.data?.items ?? []).length > 0}
                  fallback={<div class="text-sm text-dim">{t("fissures.noChats")}</div>}
                >
                  <ul class="space-y-1">
                    <For each={chats.data?.items ?? []}>
                      {(c) => <li class="text-sm text-sub">{c.username ? `@${c.username}` : c.chat_id}</li>}
                    </For>
                  </ul>
                </Show>
              </div>
              <button type="button" onClick={sendTest} class="btn-ghost w-full justify-center mt-3">
                {t("fissures.sendTest")}
              </button>
            </Show>
          </Card>
        </div>

        <Card title={t("fissures.live")}>
          <Show when={hasFilters()}>
            <div class="flex items-center justify-between mb-3 text-xs text-dim">
              <span class="num">{filteredLive().length} / {(live.data?.items ?? []).length}</span>
              <button type="button" onClick={clearFilters} class="text-dim hover:text-fg transition-colors">
                {t("fissures.clearFilters")}
              </button>
            </div>
          </Show>
          <Show
            when={filteredLive().length > 0}
            fallback={
              <EmptyState
                title={(live.data?.items ?? []).length > 0 ? t("fissures.liveNoMatch") : t("fissures.liveEmpty")}
                hint=""
              />
            }
          >
            <ul class="space-y-1.5">
              <For each={filteredLive()}>
                {(f) => (
                  <li class="flex items-center justify-between gap-2 px-3 py-2.5 rounded-[10px] hover:bg-white/[0.03] transition-colors">
                    <span class="flex flex-wrap items-center gap-2">
                      <Badge variant="info">{f.era}</Badge>
                      <span class="text-fg font-medium">{f.mission_type}</span>
                      <span class="text-dim">· {f.node}</span>
                      <Show when={f.is_hard}><Badge variant="warn">SP</Badge></Show>
                      <Show when={f.is_storm}><Badge variant="vaulted">Storm</Badge></Show>
                    </span>
                    <span class="text-xs text-dim num">{fmtEta(f.eta_seconds)}</span>
                  </li>
                )}
              </For>
            </ul>
          </Show>
        </Card>
      </div>
    </div>
  );
}
