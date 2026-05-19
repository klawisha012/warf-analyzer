import { useCallback, useEffect, useState } from 'react'

export type NotificationPermissionState =
  | 'unsupported'
  | 'default'
  | 'granted'
  | 'denied'

/**
 * Browser Notifications wrapper.
 *
 * IMPORTANT (per PLAN.md anti-patterns): we MUST NOT call
 * `Notification.requestPermission()` on mount or at module load.
 * The user must click an "Enable notifications" button to trigger `enable()`.
 */
export function useNotifications() {
  const supported = typeof window !== 'undefined' && 'Notification' in window

  const [permission, setPermission] = useState<NotificationPermissionState>(() => {
    if (!supported) return 'unsupported'
    return Notification.permission as NotificationPermissionState
  })

  // Keep state in sync if another part of the app changes permission state.
  useEffect(() => {
    if (!supported) return
    setPermission(Notification.permission as NotificationPermissionState)
  }, [supported])

  // User-gesture action. The UI must wire this to a button click, never useEffect.
  const enable = useCallback(async (): Promise<NotificationPermissionState> => {
    if (!supported) return 'unsupported'
    try {
      const result = await Notification.requestPermission()
      setPermission(result as NotificationPermissionState)
      return result as NotificationPermissionState
    } catch {
      return Notification.permission as NotificationPermissionState
    }
  }, [supported])

  const notify = useCallback(
    (title: string, opts?: NotificationOptions): Notification | null => {
      if (!supported || Notification.permission !== 'granted') return null
      try {
        return new Notification(title, opts)
      } catch {
        return null
      }
    },
    [supported],
  )

  return { supported, permission, enable, notify }
}
