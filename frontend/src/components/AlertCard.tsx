/**
 * AlertCard — production replacement for the demo AlertCardMock.
 *
 * Renders a single auction alert with:
 *  - severity pill (indigo for pod roll, green for good stats, neutral for endo),
 *  - weapon, riven mod name, price, re-rolls, ratio, owner, datetime (+3h),
 *  - StatBar per positive stat when the weapon has SYNERGIES bands,
 *  - actions: Copy owner / Copy whisper / Open auction / Save groll / Dismiss.
 */
import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Panel, StatBar } from '@/components/ui-skin'
import { api } from '@/lib/api'
import { copyToClipboard, whisperMessage } from '@/lib/format'
import { SYNERGIES, statLabel } from '@/lib/synergies'
import { cn } from '@/lib/utils'
import type { AlertReason, Auction, RivenAttribute } from '@/types'

type Props = {
  auction: Auction
  reason: AlertReason
  onSaveGroll?: () => void
  onDismiss?: () => void
  onWatch?: (weapon: string) => void
  onSelectWeapon?: (weapon: string) => void
}

const REASON_PILL: Record<AlertReason, string> = {
  'pod roll':   'border-rs-accent/30  bg-rs-accent/10  text-rs-accent',
  'good stats': 'border-rs-success/25 bg-rs-success/10 text-rs-success',
  'endo':       'border-rs-border    bg-white/[0.04] text-rs-mute',
}

function fmtDateTimePlus3(iso: string): string {
  if (!iso) return ''
  const s = iso.endsWith('Z') ? iso.replace('Z', '+00:00') : iso
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return iso
  const shifted = new Date(d.getTime() + 3 * 3600 * 1000)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return (
    `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())} ` +
    `${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}`
  )
}

function ratioStr(price: number | null | undefined, reRolls: number | null | undefined): string {
  if (!price || !reRolls) return 'fresh'
  return (reRolls / price).toFixed(2)
}

/**
 * Compute the % fill for a single positive stat.
 * Formula ported from `value_to_color` in the legacy rivenwidgets.py:
 *   normalized = val / ((rank + 1) / 9)
 *   pct = (normalized - min) / (max - min) * 100
 */
function statPct(
  weapon: string,
  attr: RivenAttribute,
  modRank: number,
): number | null {
  const bands = SYNERGIES[weapon]
  if (!bands) return null
  const band = bands[attr.url_name]
  if (!band) return null
  const [min, max] = band
  if (max <= min) return null
  const rankFactor = (modRank + 1) / 9
  const normalized = attr.value / rankFactor
  const pct = Math.round(((normalized - min) / (max - min)) * 100)
  return Math.max(0, Math.min(100, pct))
}

export function AlertCard({
  auction,
  reason,
  onSaveGroll,
  onDismiss,
  onWatch,
  onSelectWeapon,
}: Props) {
  const item = auction.item
  const weapon = item?.weapon_url_name ?? ''
  const modName = item?.name ?? ''
  const reRolls = item?.re_rolls ?? 0
  const price = auction.buyout_price ?? 0
  const owner = auction.owner?.ingame_name ?? '?'
  const priority = reason === 'pod roll'
  const showStatBars = reason === 'good stats' && weapon in SYNERGIES

  const positiveAttrs = (item?.attributes ?? []).filter((a) => a.positive)
  const negativeAttr = (item?.attributes ?? []).find((a) => !a.positive)
  const modRank = item?.mod_rank ?? 8

  const saveMutation = useMutation({
    mutationFn: async () => {
      return api<{ ok: boolean; auction_id: string }>('/api/groll', {
        method: 'POST',
        body: JSON.stringify(auction),
      })
    },
    onSuccess: () => {
      toast.success('Groll saved')
      onSaveGroll?.()
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Failed to save groll'
      toast.error(msg)
    },
  })

  const handleCopyOwner = async () => {
    const ok = await copyToClipboard(owner)
    ok ? toast.success(`Copied: ${owner}`) : toast.error('Copy failed')
  }

  const handleCopyWhisper = async () => {
    const msg = whisperMessage(owner, weapon, modName, price)
    const ok = await copyToClipboard(msg)
    ok ? toast.success('Whisper copied') : toast.error('Copy failed')
  }

  const handleOpenAuction = () => {
    window.open(`https://warframe.market/auction/${auction.id}`, '_blank', 'noopener')
  }

  return (
    <Panel
      tone={priority ? 'priority' : 'default'}
      className={cn('p-3.5 transition hover:bg-rs-panel-hi')}
    >
      {/* Header row */}
      <div className="grid grid-cols-[1fr_auto] items-start gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                'rounded-full border px-2 py-[1px] text-[10px] font-semibold capitalize',
                REASON_PILL[reason],
              )}
            >
              {reason}
            </span>
            {onSelectWeapon ? (
              <button
                type="button"
                onClick={() => onSelectWeapon(weapon)}
                className="text-[14px] font-semibold text-rs-text capitalize truncate hover:text-rs-accent hover:underline underline-offset-4 cursor-pointer"
                title={`Show ${weapon} price chart`}
              >
                {weapon}
              </button>
            ) : (
              <span className="text-[14px] font-semibold text-rs-text capitalize truncate">
                {weapon}
              </span>
            )}
            {modName && (
              <span className="truncate text-[13px] text-rs-mute">· {modName}</span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12px] text-rs-dim">
            <span>
              by <span className="text-rs-text">{owner}</span>
            </span>
            <span className="num text-rs-mute">{fmtDateTimePlus3(auction.updated)}</span>
          </div>
        </div>
        <div className="flex flex-col items-end">
          <div className="num text-[18px] font-semibold leading-none text-rs-text">
            {price}
            <span className="ml-0.5 text-[12px] text-rs-mute">p</span>
          </div>
          <div className="num mt-1 text-[11px] text-rs-mute">
            ↺ {reRolls} · {ratioStr(price, reRolls)} r/p
          </div>
        </div>
      </div>

      {/* Stat bars — only for good-stats hits on SYNERGIES weapons */}
      {showStatBars && positiveAttrs.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5 border-t border-rs-border pt-3">
          {positiveAttrs.map((attr) => {
            const pct = statPct(weapon, attr, modRank) ?? 0
            return (
              <StatBar
                key={attr.url_name}
                label={statLabel(attr.url_name)}
                value={`+${attr.value.toFixed(1)}%`}
                pct={pct}
              />
            )
          })}
          {negativeAttr && (
            <div className="mt-1 flex items-center gap-2 text-[11px] text-rs-mute">
              <span className="text-rs-danger">▼</span>
              {statLabel(negativeAttr.url_name)}
              <span className="num ml-auto text-rs-danger">{negativeAttr.value.toFixed(1)}%</span>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-rs-border pt-2.5">
        <Button
          size="sm"
          variant="outline"
          onClick={handleCopyOwner}
          className="border-rs-border bg-transparent text-rs-dim hover:bg-rs-panel-hi hover:text-rs-text text-[11px] h-7 px-2.5"
        >
          Copy owner
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleCopyWhisper}
          className="border-rs-border bg-transparent text-rs-dim hover:bg-rs-panel-hi hover:text-rs-text text-[11px] h-7 px-2.5"
        >
          Whisper
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleOpenAuction}
          className="border-rs-border bg-transparent text-rs-dim hover:bg-rs-panel-hi hover:text-rs-text text-[11px] h-7 px-2.5"
        >
          Open
        </Button>
        {onWatch && weapon && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onWatch(weapon)}
            className="border-rs-accent/30 bg-rs-accent/10 text-rs-accent hover:bg-rs-accent/20 hover:text-rs-accent text-[11px] h-7 px-2.5"
          >
            Watch
          </Button>
        )}
        {showStatBars && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="border-rs-accent/30 bg-rs-accent/10 text-rs-accent hover:bg-rs-accent/20 hover:text-rs-accent text-[11px] h-7 px-2.5"
          >
            {saveMutation.isPending ? 'Saving…' : 'Save groll'}
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          onClick={onDismiss}
          className="ml-auto text-rs-mute hover:text-rs-text text-[11px] h-7 px-2.5"
        >
          Dismiss
        </Button>
      </div>
    </Panel>
  )
}
