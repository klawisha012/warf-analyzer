import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Flat hairline-bordered surface — Slate / Linear style.
 * Replaces shadcn Card so the codebase has one consistent panel primitive.
 * The legacy `brackets` prop is preserved as a no-op for back-compat; the
 * Slate aesthetic drops corner brackets / scanlines / glow entirely.
 */
export function Panel({
  className,
  brackets: _brackets,
  tone = 'default',
  ...props
}: React.ComponentProps<'div'> & {
  brackets?: boolean
  tone?: 'default' | 'priority' | 'muted'
}) {
  void _brackets
  const toneClass =
    tone === 'priority'
      ? 'border-rs-accent/30 bg-rs-panel'
      : tone === 'muted'
      ? 'border-rs-border bg-rs-panel/70'
      : 'border-rs-border bg-rs-panel'

  return (
    <div
      data-slot="panel"
      className={cn(
        'relative rounded-lg border',
        toneClass,
        className,
      )}
      {...props}
    />
  )
}

export function PanelHeader({
  className,
  ...props
}: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="panel-header"
      className={cn(
        'flex items-center gap-3 border-b border-rs-border px-3.5 py-3',
        className,
      )}
      {...props}
    />
  )
}

export function PanelTitle({
  className,
  ...props
}: React.ComponentProps<'h3'>) {
  return (
    <h3
      data-slot="panel-title"
      className={cn(
        'text-[13px] font-semibold text-rs-text tracking-[-0.005em]',
        className,
      )}
      {...props}
    />
  )
}

export function PanelBody({
  className,
  ...props
}: React.ComponentProps<'div'>) {
  return <div data-slot="panel-body" className={cn('p-3.5', className)} {...props} />
}
