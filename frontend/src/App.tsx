import { createQuery } from "@tanstack/solid-query";
import { api } from "./api/client";

type ApiInfo = {
  name: string;
  version: string;
  docs_url: string;
  endpoints: string[];
};

type HealthResponse = {
  ok: boolean;
  wfm_username: string | null;
  aleca_version: string | null;
  cache: Record<string, unknown>;
};

export default function App() {
  const info = createQuery(() => ({
    queryKey: ["info"],
    queryFn: () => api<ApiInfo>("/"),
  }));
  const health = createQuery(() => ({
    queryKey: ["healthz"],
    queryFn: () => api<HealthResponse>("/healthz"),
    refetchInterval: 5_000,
  }));

  return (
    <main class="min-h-screen p-8 max-w-4xl mx-auto">
      <h1 class="text-3xl font-bold mb-6">
        AlecaFrame{" "}
        <span class="text-slate-400 text-base font-normal">
          backend v{info.data?.version ?? "…"}
        </span>
      </h1>

      <section class="grid grid-cols-2 gap-4 mb-8">
        <div class="rounded-2xl bg-slate-900 p-4 border border-slate-800">
          <div class="text-slate-400 text-sm">Health</div>
          <div
            class="text-xl font-semibold"
            classList={{
              "text-emerald-400": health.data?.ok === true,
              "text-rose-400": health.data?.ok === false,
              "text-slate-400": !health.data,
            }}
          >
            {health.isLoading ? "checking…" : health.data?.ok ? "online" : "offline"}
          </div>
        </div>
        <div class="rounded-2xl bg-slate-900 p-4 border border-slate-800">
          <div class="text-slate-400 text-sm">WFM user</div>
          <div class="text-xl font-mono">{health.data?.wfm_username ?? "—"}</div>
        </div>
      </section>

      <section>
        <h2 class="text-xl font-semibold mb-3">Endpoints</h2>
        <ul class="space-y-1 font-mono text-sm text-slate-300">
          {(info.data?.endpoints ?? []).map((e) => (
            <li>
              <code class="bg-slate-900 rounded px-2 py-0.5">{e}</code>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
