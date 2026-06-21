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
  const [hard, setHard] = createSignal("");
  const [storm, setStorm] = createSignal("");

  async function addSub() {
    await fetchers.fissuresSubAdd({
      era: era() || null,
      mission_type: mission() || null,
      is_hard: triToBool(hard()),
      is_storm: triToBool(storm()),
    });
    setEra(""); setMission(""); setHard(""); setStorm("");
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
          <Show
            when={(live.data?.items ?? []).length > 0}
            fallback={<EmptyState title={t("fissures.liveEmpty")} hint="" />}
          >
            <ul class="space-y-1.5">
              <For each={live.data?.items ?? []}>
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
