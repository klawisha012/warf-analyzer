/**
 * AlertsPage — production wiring.
 *
 * Hydrates from /api/alerts on mount, then streams live updates via the
 * /ws/alerts WebSocket. New alerts trigger an OS notification (only after the
 * user clicks "Enable notifications"). The hydration replay does NOT notify.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Panel,
  PanelHeader,
  PanelTitle,
  PanelBody,
  PageHeader,
  PageTitle,
  StatChip,
} from '@/components/ui-skin'
import { AlertCard } from '@/components/AlertCard'
import { PriceChart } from '@/components/PriceChart'
import { WeaponPicker } from '@/components/WeaponPicker'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useNotifications } from '@/hooks/useNotifications'
import { api } from '@/lib/api'
import type { AlertItem, Auction } from '@/types'

const MAX_ALERTS = 200

type WsAlertMessage = {
  type: 'alert'
  auction: Auction
  reason: AlertItem['reason']
}

type WsStatsMessage = {
  type: 'stats'
  api_updates: number
}

type WsMessage = WsAlertMessage | WsStatsMessage | Record<string, unknown>

function dedupeFront(list: AlertItem[]): AlertItem[] {
  const seen = new Set<string>()
  const out: AlertItem[] = []
  for (const item of list) {
    const id = item.auction?.id
    if (!id || seen.has(id)) continue
    seen.add(id)
    out.push(item)
  }
  return out
}

export function AlertsPage() {
  const queryClient = useQueryClient()
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [apiUpdates, setApiUpdates] = useState(0)
  const [selectedWeapon, setSelectedWeapon] = useState<string | null>(null)
  const hydratedRef = useRef(false)

  const { permission, enable, notify } = useNotifications()

  const addToWatchlist = useMutation({
    mutationFn: async (weapon: string) =>
      api<{ weapon: string; added: boolean }>('/api/watchlist', {
        method: 'POST',
        body: JSON.stringify({ weapon }),
      }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ['watchlist'] })
      toast.success(
        data.added
          ? `Added ${data.weapon} to watchlist`
          : `${data.weapon} already in watchlist`,
      )
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Save failed'
      toast.error(msg)
    },
  })

  const dismissAlert = useMutation({
    mutationFn: async (auctionId: string) =>
      api<{ auction_id: string; dismissed: boolean }>(
        `/api/alerts/${encodeURIComponent(auctionId)}`,
        { method: 'DELETE' },
      ),
    onError: (err: unknown) => {
      // Silent on failure — local state already removed; worst case the alert
      // re-appears on next reload, surface a quiet toast for visibility.
      const msg = err instanceof Error ? err.message : 'Dismiss not persisted'
      toast.error(msg)
    },
  })

  // ── Hydration ──────────────────────────────────────────────────────────
  const hydrate = useQuery({
    queryKey: ['alerts'],
    queryFn: () => api<AlertItem[]>('/api/alerts?limit=50'),
  })

  useEffect(() => {
    if (!hydrate.data || hydratedRef.current) return
    // copy: never mutate useQuery data
    const initial = dedupeFront(hydrate.data.slice())
    setAlerts(initial.slice(0, MAX_ALERTS))
    hydratedRef.current = true
  }, [hydrate.data])

  // ── Live WS feed ───────────────────────────────────────────────────────
  const { status, lastMessage } = useWebSocket('/ws/alerts')

  useEffect(() => {
    if (!lastMessage || typeof lastMessage !== 'object') return
    const msg = lastMessage as WsMessage
    if (msg.type === 'alert' && (msg as WsAlertMessage).auction) {
      const incoming = msg as WsAlertMessage
      const item: AlertItem = {
        type: 'alert',
        auction: incoming.auction,
        reason: incoming.reason,
        ts: Date.now() / 1000,
      }
      let isNew = false
      setAlerts((prev) => {
        if (prev.some((a) => a.auction?.id === item.auction.id)) return prev
        isNew = true
        return [item, ...prev].slice(0, MAX_ALERTS)
      })
      // Notify only for genuinely new alerts received over the live stream
      // (we tracked `isNew` synchronously in the setter).
      if (isNew && hydratedRef.current && permission === 'granted') {
        const w = item.auction.item?.weapon_url_name ?? 'riven'
        notify(`${item.reason.toUpperCase()} · ${w}`, {
          body: `${item.auction.buyout_price ?? '?'}p · ${item.auction.owner?.ingame_name ?? '?'}`,
        })
      }
    } else if (msg.type === 'stats') {
      const stats = msg as WsStatsMessage
      if (typeof stats.api_updates === 'number') {
        setApiUpdates(stats.api_updates)
      }
    }
  }, [lastMessage, notify, permission])

  // ── Counter derivations ────────────────────────────────────────────────
  const priorityCount = useMemo(
    () => alerts.filter((a) => a.reason === 'pod roll').length,
    [alerts],
  )
  const goodStatsCount = useMemo(
    () => alerts.filter((a) => a.reason === 'good stats').length,
    [alerts],
  )

  const handleDismiss = (id: string) => {
    // Optimistic local removal — server call persists it so reload won't
    // resurrect the card from the deque.
    setAlerts((prev) => prev.filter((a) => a.auction?.id !== id))
    dismissAlert.mutate(id)
  }
  const handleSaved = (id: string) => {
    // Save-groll POST already drops the entry from app.state.recent_alerts
    // on the server side (see routes/groll.py), so local optimistic removal
    // is enough — no extra DELETE call needed.
    setAlerts((prev) => prev.filter((a) => a.auction?.id !== id))
  }

  const handleEnableNotifications = () => {
    void enable()
  }

  return (
    <div className="space-y-6">
      <PageHeader>
        <PageTitle
          eyebrow={status === 'open' ? 'Live · connected' : `Connection: ${status}`}
          title="Auction stream"
          subtitle="Live riven feed — warframe.market · PC"
          liveDot={status === 'open'}
        />
        <div className="flex flex-wrap items-stretch gap-2">
          <StatChip label="API ticks" value={apiUpdates} live={status === 'open'} />
          <StatChip label="Alerts" value={alerts.length} tone="positive" />
          <StatChip label="Priority" value={priorityCount} tone="priority" />
          <StatChip label="Good stats" value={goodStatsCount} />
        </div>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        {/* LEFT — alerts list */}
        <Panel>
          <PanelHeader>
            <PanelTitle>Incoming auctions</PanelTitle>
            <span className="num ml-auto text-[12px] text-rs-mute">
              {alerts.length} / {MAX_ALERTS}
            </span>
          </PanelHeader>
          <PanelBody className="p-0">
            <ScrollArea className="h-[640px]">
              <div className="flex flex-col gap-2 p-3">
                {alerts.length === 0 && (
                  <div className="py-12 text-center text-[12px] text-rs-mute">
                    {hydrate.isPending
                      ? 'Loading recent alerts…'
                      : status === 'open'
                        ? 'Waiting for alerts…'
                        : 'No alerts yet (offline).'}
                  </div>
                )}
                {alerts.map((a) => (
                  <AlertCard
                    key={a.auction.id}
                    auction={a.auction}
                    reason={a.reason}
                    onSaveGroll={() => handleSaved(a.auction.id)}
                    onDismiss={() => handleDismiss(a.auction.id)}
                    onWatch={(w) => addToWatchlist.mutate(w)}
                    onSelectWeapon={setSelectedWeapon}
                  />
                ))}
              </div>
            </ScrollArea>
          </PanelBody>
        </Panel>

        {/* RIGHT — weapon picker + chart (also driven by clicking a card weapon) + notifications */}
        <div className="flex flex-col gap-4">
          <WeaponPicker value={selectedWeapon} onChange={setSelectedWeapon} />
          <PriceChart weapon={selectedWeapon} />

          <Panel tone="muted">
            <PanelBody className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[13px] font-semibold text-rs-text">
                  Browser notifications
                </div>
                <div className="mt-1 text-[12px] text-rs-mute">
                  Status: <span className="num text-rs-dim">{permission}</span>. Required for OS-level alerts.
                </div>
              </div>
              <Button
                size="sm"
                onClick={handleEnableNotifications}
                disabled={permission === 'granted' || permission === 'unsupported'}
                className="bg-rs-accent text-[oklch(0.10_0.040_280)] hover:bg-rs-accent/90"
              >
                {permission === 'granted' ? 'Enabled' : 'Enable'}
              </Button>
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
  )
}
