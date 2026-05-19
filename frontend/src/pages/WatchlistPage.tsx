/**
 * WatchlistPage — pinned weapons + latest price snapshot.
 *
 * Backed by /api/watchlist (single AppSetting row, enriched server-side with
 * the most recent WeaponPriceSample row per weapon). Pin via the
 * "Save to watchlist" button on the Alerts page; unpin from here.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Panel,
  PanelHeader,
  PanelTitle,
  PanelBody,
  PageHeader,
  PageTitle,
} from '@/components/ui-skin'
import { api } from '@/lib/api'
import { fmtTime } from '@/lib/format'
import type { WatchlistEntry } from '@/types'

export function WatchlistPage() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => api<WatchlistEntry[]>('/api/watchlist'),
    refetchInterval: 30_000,
  })

  const remove = useMutation({
    mutationFn: async (weapon: string) =>
      api<{ weapon: string; removed: boolean }>(
        `/api/watchlist/${encodeURIComponent(weapon)}`,
        { method: 'DELETE' },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['watchlist'] })
      toast.success('Removed from watchlist')
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Remove failed'
      toast.error(msg)
    },
  })

  const entries = query.data ?? []

  return (
    <div className="space-y-6">
      <PageHeader>
        <PageTitle
          eyebrow="Watching"
          title="Watchlist"
          subtitle="Pinned weapons + most recent market snapshot."
        />
      </PageHeader>

      <Panel>
        <PanelHeader>
          <PanelTitle>Pinned weapons</PanelTitle>
          <span className="num ml-auto text-[12px] text-rs-mute">
            {entries.length} pinned
          </span>
        </PanelHeader>
        <PanelBody className="p-0">
          {query.isPending ? (
            <div className="py-10 text-center text-[12px] text-rs-mute">Loading…</div>
          ) : query.isError ? (
            <div className="py-10 text-center text-[12px] text-rs-danger">
              Failed to load watchlist.
            </div>
          ) : entries.length === 0 ? (
            <div className="py-10 text-center text-[12px] text-rs-mute">
              Nothing pinned yet. From the Alerts tab, pick a weapon in the
              price-chart panel and click <span className="text-rs-dim">“Save to watchlist”</span>.
            </div>
          ) : (
            <ul className="divide-y divide-rs-border">
              {entries.map((e) => (
                <li
                  key={e.weapon}
                  className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 px-4 py-2.5"
                >
                  <span className="text-[13px] text-rs-text capitalize truncate">
                    {e.weapon}
                  </span>
                  <span className="num text-[13px] text-rs-text text-right tabular-nums">
                    {e.p1 != null ? (
                      <>
                        {e.p1}
                        <span className="text-rs-mute text-[11px]">p</span>
                        {e.p2 != null && e.p3 != null && (
                          <span className="ml-2 text-rs-mute text-[11px]">
                            · {e.p2}p / {e.p3}p
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-rs-mute text-[11px]">—</span>
                    )}
                  </span>
                  <span className="num text-[11px] text-rs-mute text-right min-w-[120px]">
                    {e.latest_ts ? fmtTime(e.latest_ts) : ''}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => remove.mutate(e.weapon)}
                    disabled={remove.isPending}
                    className="border-rs-border bg-transparent text-rs-mute hover:bg-rs-panel-hi hover:text-rs-danger text-[11px] h-7 px-3"
                  >
                    Remove
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
