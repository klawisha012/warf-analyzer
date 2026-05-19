/**
 * SettingsPage — Pod-roll weapons, Fast-scan weapons, Saved grolls.
 *
 * Each textarea is its own form (separate Save button, separate mutation).
 * On save, validates parse, surfaces inline errors, then PUTs the full
 * /api/settings payload (the backend uses replace-semantics on both keys).
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Panel,
  PanelHeader,
  PanelTitle,
  PanelBody,
  PageHeader,
  PageTitle,
} from '@/components/ui-skin'
import { api } from '@/lib/api'
import type { Settings } from '@/types'

type ParsedGood = { ok: true; map: Record<string, number> } | { ok: false; errors: string[] }
type ParsedFast = { ok: true; list: string[] } | { ok: false; errors: string[] }

function parseGoodWeapons(text: string): ParsedGood {
  const errors: string[] = []
  const map: Record<string, number> = {}
  const lines = text.split('\n')
  lines.forEach((raw, idx) => {
    const line = raw.trim()
    if (!line) return
    const parts = line.split(/\s+/).filter(Boolean)
    if (parts.length !== 2) {
      errors.push(`Line ${idx + 1}: expected "weapon_url_name price"`)
      return
    }
    const [weapon, priceStr] = parts
    const price = Number(priceStr)
    if (!Number.isFinite(price) || Number.isNaN(price)) {
      errors.push(`Line ${idx + 1}: invalid price "${priceStr}"`)
      return
    }
    map[weapon] = price
  })
  return errors.length ? { ok: false, errors } : { ok: true, map }
}

function parseFastWeapons(text: string): ParsedFast {
  const list: string[] = []
  const errors: string[] = []
  text.split('\n').forEach((raw, idx) => {
    const line = raw.trim()
    if (!line) return
    if (/\s/.test(line)) {
      errors.push(`Line ${idx + 1}: weapon name must be a single token`)
      return
    }
    list.push(line)
  })
  return errors.length ? { ok: false, errors } : { ok: true, list }
}

function formatGood(map: Record<string, number>): string {
  return Object.entries(map)
    .map(([w, p]) => `${w} ${p}`)
    .join('\n')
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => api<Settings>('/api/settings'),
  })

  const [goodText, setGoodText] = useState('')
  const [fastText, setFastText] = useState('')
  const [goodErrors, setGoodErrors] = useState<string[]>([])
  const [fastErrors, setFastErrors] = useState<string[]>([])

  // Seed textareas once data lands. Re-seed if the query result changes
  // (e.g. after a successful save invalidates 'settings').
  useEffect(() => {
    if (!settingsQuery.data) return
    setGoodText(formatGood(settingsQuery.data.good_weapons ?? {}))
    setFastText((settingsQuery.data.fast_weapons_list ?? []).join('\n'))
  }, [settingsQuery.data])

  const saveMutation = useMutation({
    mutationFn: async (payload: Settings) =>
      api<Settings>('/api/settings', {
        method: 'PUT',
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      toast.success('Settings saved')
      void queryClient.invalidateQueries({ queryKey: ['weapons'] })
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Save failed'
      toast.error(msg)
    },
  })

  const resetMutation = useMutation({
    mutationFn: async () =>
      api<Settings>('/api/settings/reset-to-defaults', { method: 'POST' }),
    onSuccess: () => {
      toast.success('Restored from settings.json')
      setGoodErrors([])
      setFastErrors([])
      void queryClient.invalidateQueries({ queryKey: ['weapons'] })
      void queryClient.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Reset failed'
      toast.error(msg)
    },
  })

  const handleSaveGood = () => {
    const parsed = parseGoodWeapons(goodText)
    if (!parsed.ok) {
      setGoodErrors(parsed.errors)
      toast.error(`Pod-roll list has ${parsed.errors.length} error(s)`)
      return
    }
    setGoodErrors([])
    const current = settingsQuery.data
    if (!current) return
    saveMutation.mutate({
      good_weapons: parsed.map,
      fast_weapons_list: current.fast_weapons_list ?? [],
    })
  }

  const handleSaveFast = () => {
    const parsed = parseFastWeapons(fastText)
    if (!parsed.ok) {
      setFastErrors(parsed.errors)
      toast.error(`Fast-scan list has ${parsed.errors.length} error(s)`)
      return
    }
    setFastErrors([])
    const current = settingsQuery.data
    if (!current) return
    saveMutation.mutate({
      good_weapons: current.good_weapons ?? {},
      fast_weapons_list: parsed.list,
    })
  }

  // ── Saved grolls ───────────────────────────────────────────────────────
  const grollsQuery = useQuery({
    queryKey: ['groll'],
    queryFn: () => api<string[]>('/api/groll'),
  })

  const deleteGroll = useMutation({
    mutationFn: async (id: string) =>
      api<{ ok: boolean }>(`/api/groll/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      toast.success('Groll deleted')
      void queryClient.invalidateQueries({ queryKey: ['groll'] })
    },
    onError: () => toast.error('Delete failed'),
  })

  return (
    <div className="space-y-6">
      <PageHeader>
        <PageTitle
          eyebrow="Configuration"
          title="Settings"
          subtitle="Pod-roll thresholds, fast-scan list, and saved grolls."
        />
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            if (window.confirm('Reset good_weapons + fast_weapons_list to the bundled settings.json defaults? (Watchlist is not affected.)')) {
              resetMutation.mutate()
            }
          }}
          disabled={resetMutation.isPending}
          className="border-rs-border bg-transparent text-rs-dim hover:bg-rs-panel-hi hover:text-rs-text text-[12px] h-8 self-end"
        >
          {resetMutation.isPending ? 'Resetting…' : 'Reset to defaults'}
        </Button>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Pod-roll weapons */}
        <Panel>
          <PanelHeader>
            <PanelTitle>Pod-roll weapons</PanelTitle>
            <span className="num ml-auto text-[12px] text-rs-mute">
              weapon_url_name &nbsp; price
            </span>
          </PanelHeader>
          <PanelBody className="space-y-3">
            <Textarea
              value={goodText}
              onChange={(e) => setGoodText(e.target.value)}
              className="font-mono min-h-[280px] bg-rs-panel-hi border-rs-border text-[12px] leading-relaxed"
              placeholder="bramma 350&#10;tonkor 280"
              spellCheck={false}
            />
            {goodErrors.length > 0 && (
              <div className="rounded-md border border-rs-danger/40 bg-rs-danger/10 p-2 text-[12px] text-rs-danger">
                {goodErrors.map((e, i) => (
                  <div key={i}>{e}</div>
                ))}
              </div>
            )}
            <div className="flex justify-end">
              <Button
                size="sm"
                onClick={handleSaveGood}
                disabled={saveMutation.isPending || settingsQuery.isPending}
                className="bg-rs-accent text-[oklch(0.10_0.040_280)] hover:bg-rs-accent/90"
              >
                {saveMutation.isPending ? 'Saving…' : 'Save pod-roll list'}
              </Button>
            </div>
          </PanelBody>
        </Panel>

        {/* Fast-scan weapons */}
        <Panel>
          <PanelHeader>
            <PanelTitle>Fast-scan weapons</PanelTitle>
            <span className="num ml-auto text-[12px] text-rs-mute">
              one per line
            </span>
          </PanelHeader>
          <PanelBody className="space-y-3">
            <Textarea
              value={fastText}
              onChange={(e) => setFastText(e.target.value)}
              className="font-mono min-h-[280px] bg-rs-panel-hi border-rs-border text-[12px] leading-relaxed"
              placeholder="bramma&#10;tonkor"
              spellCheck={false}
            />
            {fastErrors.length > 0 && (
              <div className="rounded-md border border-rs-danger/40 bg-rs-danger/10 p-2 text-[12px] text-rs-danger">
                {fastErrors.map((e, i) => (
                  <div key={i}>{e}</div>
                ))}
              </div>
            )}
            <div className="flex justify-end">
              <Button
                size="sm"
                onClick={handleSaveFast}
                disabled={saveMutation.isPending || settingsQuery.isPending}
                className="bg-rs-accent text-[oklch(0.10_0.040_280)] hover:bg-rs-accent/90"
              >
                {saveMutation.isPending ? 'Saving…' : 'Save fast-scan list'}
              </Button>
            </div>
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader>
          <PanelTitle>Saved grolls</PanelTitle>
          <span className="num ml-auto text-[12px] text-rs-mute">
            {grollsQuery.data?.length ?? 0} saved
          </span>
        </PanelHeader>
        <PanelBody>
          {grollsQuery.isPending ? (
            <div className="py-8 text-center text-[12px] text-rs-mute">Loading…</div>
          ) : grollsQuery.isError ? (
            <div className="py-8 text-center text-[12px] text-rs-danger">
              Failed to load saved grolls.
            </div>
          ) : !grollsQuery.data || grollsQuery.data.length === 0 ? (
            <div className="py-8 text-center text-[12px] text-rs-mute">
              No saved grolls yet.
            </div>
          ) : (
            <ul className="divide-y divide-rs-border">
              {grollsQuery.data.map((id) => (
                <li
                  key={id}
                  className="flex items-center justify-between gap-3 py-2.5"
                >
                  <div className="min-w-0">
                    <span className="num text-[12px] text-rs-dim truncate">{id}</span>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => deleteGroll.mutate(id)}
                    disabled={deleteGroll.isPending}
                    className="border-rs-border bg-transparent text-rs-mute hover:bg-rs-panel-hi hover:text-rs-danger text-[11px] h-7 px-3"
                  >
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </PanelBody>
      </Panel>
    </div>
  )
}
