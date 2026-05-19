// Shared formatting + clipboard helpers used by Alerts cards and chart axes.

export function fmtTime(unixSec: number): string {
  if (!Number.isFinite(unixSec)) return ''
  const d = new Date(unixSec * 1000)
  // Display in local time; the backend already adjusts for warframe.market's UTC+3 quirk.
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
    // Fallback for non-secure contexts (rare): create a hidden textarea.
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

// Mirrors the in-game whisper format from the legacy desktop app.
export function whisperMessage(
  owner: string,
  weapon: string,
  rivenName: string,
  price: number | null | undefined,
): string {
  const priceStr = price == null ? '?' : String(price)
  return `/w ${owner} Hi! I want to buy: "${weapon} ${rivenName}" for ${priceStr} platinum. (warframe.market)`
}
