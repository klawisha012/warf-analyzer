import { cn } from '@/lib/utils'
import { statColor } from './tokens'

/**
 * Horizontal stat bar with a 0–100 fill (Slate ramp: warn → success → accent).
 * Pure presentational — the parent owns the value math (the backend / card
 * computes the normalized percentage via the SYNERGIES bands).
 */
export function StatBar({
  label,
  value,           // raw stat value, e.g. "+128.4%"
  pct,             // normalized 0–100 (drives the bar fill)
  negative = false,
  className,
}: {
  label: string
  value: string
  pct: number
  negative?: boolean
  className?: string
}) {
  const clamped = Math.max(0, Math.min(100, pct))
  const labelColor = statColor(clamped)

  return (
    <div
      className={cn(
        'grid grid-cols-[160px_1fr_64px] items-center gap-x-3',
        className,
      )}
    >
      <span
        className={cn(
          'truncate text-[12px]',
          negative ? 'text-rs-danger/85' : 'text-rs-dim',
        )}
        title={label}
      >
        {negative && <span className="mr-1 text-rs-danger">▼</span>}
        {label}
      </span>
      <div className="h-[4px] overflow-hidden rounded-[2px] bg-rs-border-hi">
        <div
          className="h-full rs-stat-fill transition-[width] duration-500"
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span
        className="num text-[11px] text-right"
        style={{ color: labelColor }}
      >
        {value}
      </span>
    </div>
  )
}
