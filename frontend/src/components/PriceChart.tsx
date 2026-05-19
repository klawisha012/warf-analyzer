/**
 * PriceChart — Recharts wrapper over /api/weapons/{weapon}/prices.
 *
 * Pipeline:
 *   1. Fetch via TanStack Query (object form, isPending).
 *   2. Take only the `p1` series.
 *   3. filterDownwardOutliers — replace anomalously-low samples with null.
 *   4. insertGaps — insert a null point before any consecutive gap > 30 min
 *      so the line breaks instead of bridging dead air.
 *   5. Render with connectNulls={false} so the null sentinels do their job.
 */
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Brush,
  ResponsiveContainer,
} from 'recharts'

import { Button } from '@/components/ui/button'
import { Panel, PanelHeader, PanelTitle, PanelBody, palette } from '@/components/ui-skin'
import { api } from '@/lib/api'
import { fmtTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { WeaponPricePoint } from '@/types'

type Props = { weapon: string | null }

type ChartPoint = { t: number; price: number | null }

type RangePreset = { label: string; seconds: number | null }

const PRESETS: RangePreset[] = [
  { label: '1D', seconds: 86_400 },
  { label: '1W', seconds: 7 * 86_400 },
  { label: '1M', seconds: 30 * 86_400 },
]

/** Index of the first point whose `t` falls within `[lastT - seconds, lastT]`. */
function indexForCutoff(points: ChartPoint[], seconds: number | null): number {
  if (seconds === null || points.length === 0) return 0
  const lastT = points[points.length - 1].t
  const cutoff = lastT - seconds
  for (let i = 0; i < points.length; i++) {
    if (points[i].t >= cutoff) return i
  }
  return Math.max(0, points.length - 1)
}

// ─── Pure helpers (ported from legacy myplot.py) ────────────────────────────

/**
 * For each sample, look at the [i-window, i+window] neighborhood (excluding
 * self), take the median of the neighbor prices, and null the sample if it is
 * either:
 *   - below `median * (1 - threshold)` (downward outlier), or
 *   - below the absolute floor `20` (warframe.market noise / mispricing).
 */
export function filterDownwardOutliers(
  times: number[],
  prices: number[],
  window = 200,
  threshold = 0.3,
): (number | null)[] {
  const n = prices.length
  const out: (number | null)[] = prices.slice()
  for (let i = 0; i < n; i++) {
    const lo = Math.max(0, i - window)
    const hi = Math.min(n, i + window + 1)
    const neighbors: number[] = []
    for (let j = lo; j < hi; j++) {
      if (j === i) continue
      neighbors.push(prices[j])
    }
    if (neighbors.length === 0) continue
    const sorted = neighbors.slice().sort((a, b) => a - b)
    const mid = Math.floor(sorted.length / 2)
    const median =
      sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
    if (prices[i] < median * (1 - threshold) || prices[i] < 20) {
      out[i] = null
    }
  }
  // keep `times` reference so signature mirrors the legacy (times unused here)
  void times
  return out
}

/**
 * For each consecutive pair where `t[i] - t[i-1] > maxGap` seconds, insert a
 * synthetic `{t: t[i], price: null}` BEFORE the real point so the X axis stays
 * monotonic and Recharts breaks the line at the gap.
 */
export function insertGaps(
  times: number[],
  prices: (number | null)[],
  maxGap = 1800,
): ChartPoint[] {
  const out: ChartPoint[] = []
  for (let i = 0; i < times.length; i++) {
    if (i > 0 && times[i] - times[i - 1] > maxGap) {
      out.push({ t: times[i], price: null })
    }
    out.push({ t: times[i], price: prices[i] })
  }
  return out
}

// ─── Component ──────────────────────────────────────────────────────────────

export function PriceChart({ weapon }: Props) {
  const query = useQuery({
    queryKey: ['weapon-prices', weapon],
    enabled: !!weapon,
    queryFn: () => api<WeaponPricePoint[]>(`/api/weapons/${weapon}/prices`),
  })

  const points: ChartPoint[] = useMemo(() => {
    if (!query.data || query.data.length === 0) return []
    // copy — never mutate useQuery data
    const sorted = query.data.slice().sort((a, b) => a.t - b.t)
    const times = sorted.map((p) => p.t)
    const p1 = sorted.map((p) => p.p1)
    const filtered = filterDownwardOutliers(times, p1)
    return insertGaps(times, filtered)
  }, [query.data])

  // Brush range — controlled by either user dragging or the preset buttons.
  // Indices reset to the full range whenever the dataset changes (new weapon
  // or refetch returned a different length).
  const [startIndex, setStartIndex] = useState(0)
  const [endIndex, setEndIndex] = useState(0)
  const [activePreset, setActivePreset] = useState<string | null>(null)

  useEffect(() => {
    if (points.length === 0) {
      setStartIndex(0)
      setEndIndex(0)
      setActivePreset(null)
      return
    }
    setStartIndex(0)
    setEndIndex(points.length - 1)
    setActivePreset(null)
  }, [points.length])

  const applyPreset = (preset: RangePreset) => {
    if (points.length === 0) return
    const start = indexForCutoff(points, preset.seconds)
    setStartIndex(start)
    setEndIndex(points.length - 1)
    setActivePreset(preset.label)
  }

  const reset = () => {
    if (points.length === 0) return
    setStartIndex(0)
    setEndIndex(points.length - 1)
    setActivePreset(null)
  }

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Price history — {weapon ?? '—'}</PanelTitle>
        <span className="num ml-auto text-[12px] text-rs-mute">
          {points.length ? `${points.length} pts` : ''}
        </span>
      </PanelHeader>
      <PanelBody>
        {!weapon ? (
          <div className="flex h-[320px] items-center justify-center text-[12px] text-rs-mute">
            Pick a weapon to view its price history.
          </div>
        ) : query.isPending ? (
          <div className="flex h-[320px] items-center justify-center text-[12px] text-rs-mute">
            Loading…
          </div>
        ) : query.isError ? (
          <div className="flex h-[320px] items-center justify-center text-[12px] text-rs-danger">
            Failed to load price history.
          </div>
        ) : points.length === 0 ? (
          <div className="flex h-[320px] items-center justify-center text-[12px] text-rs-mute">
            No samples for this weapon yet.
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={palette.border} strokeDasharray="3 3" />
                <XAxis
                  dataKey="t"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={fmtTime}
                  stroke={palette.mute}
                  tick={{ fontSize: 10, fontFamily: 'Geist Mono' }}
                />
                <YAxis
                  stroke={palette.mute}
                  tick={{ fontSize: 10, fontFamily: 'Geist Mono' }}
                />
                <Tooltip
                  labelFormatter={(label) =>
                    typeof label === 'number' ? fmtTime(label) : String(label ?? '')
                  }
                  contentStyle={{
                    background: 'var(--rs-panel-hi)',
                    border: '1px solid var(--rs-border)',
                    borderRadius: 8,
                    fontFamily: 'Geist Mono',
                    fontSize: 11,
                  }}
                  labelStyle={{ color: 'var(--rs-dim)' }}
                />
                <Line
                  type="monotone"
                  dataKey="price"
                  stroke={palette.accent}
                  strokeWidth={1.6}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Brush
                  dataKey="t"
                  height={26}
                  startIndex={startIndex}
                  endIndex={endIndex}
                  stroke={palette.accent}
                  fill="var(--rs-panel-hi)"
                  travellerWidth={8}
                  tickFormatter={(v) => fmtTime(v as number)}
                  onChange={(range) => {
                    if (typeof range.startIndex === 'number') setStartIndex(range.startIndex)
                    if (typeof range.endIndex === 'number') setEndIndex(range.endIndex)
                    // User-driven drag clears the active preset highlight.
                    setActivePreset(null)
                  }}
                />
              </LineChart>
            </ResponsiveContainer>

            {/* Range presets + reset */}
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {PRESETS.map((p) => {
                const active = activePreset === p.label
                return (
                  <Button
                    key={p.label}
                    size="sm"
                    variant="outline"
                    onClick={() => applyPreset(p)}
                    className={cn(
                      'h-7 px-3 text-[11px]',
                      active
                        ? 'border-rs-accent/40 bg-rs-accent/10 text-rs-accent hover:bg-rs-accent/15 hover:text-rs-accent'
                        : 'border-rs-border bg-transparent text-rs-dim hover:bg-rs-panel-hi hover:text-rs-text',
                    )}
                  >
                    {p.label}
                  </Button>
                )
              })}
              <Button
                size="sm"
                variant="outline"
                onClick={reset}
                disabled={
                  activePreset === null && startIndex === 0 && endIndex === points.length - 1
                }
                className="ml-auto h-7 px-3 text-[11px] border-rs-border bg-transparent text-rs-dim hover:bg-rs-panel-hi hover:text-rs-text"
              >
                Reset
              </Button>
            </div>
          </>
        )}
      </PanelBody>
    </Panel>
  )
}
