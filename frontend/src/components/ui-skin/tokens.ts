/**
 * RIVEN SCANNER — design tokens (Slate)
 *
 * Drop-in replacement for the previous Tenno-HUD palette.
 * Mirrors the CSS custom properties declared in `src/index.css` (Slate
 * edition). Use these only when JS needs a literal color value (Recharts
 * stroke, chart axes, dynamic interpolation). For styling, prefer Tailwind
 * utility classes that read the same vars.
 */

export const palette = {
  bg:         'var(--rs-bg)',
  panel:      'var(--rs-panel)',
  panelHi:    'var(--rs-panel-hi)',
  border:     'var(--rs-border)',
  borderHi:   'var(--rs-border-hi)',

  text:       'var(--rs-text)',
  dim:        'var(--rs-dim)',
  mute:       'var(--rs-mute)',

  accent:     'var(--rs-accent)',
  accentDim:  'var(--rs-accent-dim)',

  success:    'var(--rs-success)',
  warn:       'var(--rs-warn)',
  danger:     'var(--rs-danger)',

  // Back-compat aliases so call-sites that still reference the old token
  // names (`palette.cyan`, `palette.line`, `palette.textMute`) keep
  // compiling while the codebase migrates. Safe to delete once clean.
  cyan:       'var(--rs-accent)',
  cyanSoft:   'var(--rs-accent-dim)',
  orange:     'var(--rs-accent)',     // priority is now indigo
  orangeSoft: 'var(--rs-accent-dim)',
  line:       'var(--rs-border)',
  lineStrong: 'var(--rs-border-hi)',
  textDim:    'var(--rs-dim)',
  textMute:   'var(--rs-mute)',
  panelElev:  'var(--rs-panel-hi)',
  red:        'var(--rs-danger)',
  amber:      'var(--rs-warn)',
  green:      'var(--rs-success)',
} as const

export const font = {
  sans:    'var(--font-sans)',
  mono:    'var(--font-mono)',
  heading: 'var(--font-heading)',
} as const

/**
 * Severity → accent color.
 *   "pod roll"   : indigo (priority CTA)
 *   "good stats" : success green (regular HUD)
 *   "endo"       : mute (neutral / dispose)
 */
export type AlertReason = 'good stats' | 'pod roll' | 'endo' | 'none'

export const reasonAccent: Record<AlertReason, string> = {
  'pod roll':   palette.accent,
  'good stats': palette.success,
  'endo':       palette.mute,
  'none':       palette.mute,
}

/**
 * Map a 0–100 stat value to a warn → success → accent ramp. Slate moves
 * away from the red/amber/green stoplight because nothing on this surface
 * is ever truly "bad" — it's all gradations of quality.
 */
export function statColor(pct: number): string {
  const clamped = Math.max(0, Math.min(100, pct))
  if (clamped < 40) return palette.warn
  if (clamped < 75) return palette.success
  return palette.accent
}
