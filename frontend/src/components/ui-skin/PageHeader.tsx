import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Page-level header strip. Hosts the page title on the left and a row of
 * inline counter pills on the right (API ticks, alert count, live status).
 */
export function PageHeader({
  className,
  ...props
}: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="page-header"
      className={cn(
        'flex flex-wrap items-end justify-between gap-3 border-b border-rs-border pb-4',
        className,
      )}
      {...props}
    />
  )
}

/**
 * Slate eyebrow: sentence-case, with an optional pulsing dot for live state.
 * Example: `<PageTitle eyebrow="Live · connected" title="Auction stream" />`.
 */
export function PageTitle({
  eyebrow,
  title,
  subtitle,
  liveDot = false,
}: {
  eyebrow?: string
  title: string
  subtitle?: string
  liveDot?: boolean
}) {
  return (
    <div>
      {eyebrow && (
        <div className="flex items-center gap-2 text-[12px] text-rs-dim">
          {liveDot && (
            <span className="inline-block size-1.5 rounded-full bg-rs-success" />
          )}
          {eyebrow}
        </div>
      )}
      <h2 className="mt-1 text-[22px] font-semibold leading-tight text-rs-text tracking-[-0.01em]">
        {title}
      </h2>
      {subtitle && (
        <p className="mt-1 text-[13px] text-rs-mute">
          {subtitle}
        </p>
      )}
    </div>
  )
}

/**
 * Compact value chip — label on top, monospace value below.
 * Use 3–5 of these in a row for the page-header counter strip.
 */
export function StatChip({
  label,
  value,
  tone = 'default',
  live = false,
}: {
  label: string
  value: React.ReactNode
  tone?: 'default' | 'priority' | 'positive'
  live?: boolean
}) {
  const accent =
    tone === 'priority'
      ? 'text-rs-accent'
      : tone === 'positive'
      ? 'text-rs-success'
      : 'text-rs-text'

  return (
    <div className="flex flex-col gap-0.5 rounded-md border border-rs-border bg-rs-panel px-3 py-2 min-w-[88px]">
      <div className="flex items-center gap-1.5 text-[10px] text-rs-mute tracking-[0.04em]">
        {live && (
          <span className="inline-block size-1.5 rounded-full bg-rs-success" />
        )}
        {label}
      </div>
      <div className={cn('num text-[15px] font-semibold leading-none', accent)}>
        {value}
      </div>
    </div>
  )
}
