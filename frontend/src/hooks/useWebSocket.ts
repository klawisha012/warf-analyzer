import { useEffect, useRef, useState } from 'react'

export type WsStatus = 'connecting' | 'open' | 'closed'

export interface UseWebSocketOptions {
  // Time in ms between reconnect attempts. Defaults to 2_000.
  reconnectDelayMs?: number
  // Optional onMessage callback fired in addition to lastMessage state.
  onMessage?: (data: unknown) => void
}

/**
 * Minimal plain-WebSocket hook with auto-reconnect.
 *
 * Per PLAN.md anti-patterns:
 *  - The socket lives in `useRef` (storing it in state would tear it down on re-render).
 *  - Reconnect logic fires from `onclose` only — never from `onerror`.
 *  - Cleanup sets `shouldReconnect = false` and clears any pending timer.
 *  - `readyState === OPEN` is checked before every `send`.
 */
export function useWebSocket(path: string, opts: UseWebSocketOptions = {}) {
  const { reconnectDelayMs = 2000, onMessage } = opts
  const [status, setStatus] = useState<WsStatus>('connecting')
  const [lastMessage, setLastMessage] = useState<unknown>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const shouldReconnectRef = useRef(true)
  const reconnectTimerRef = useRef<number | null>(null)
  const onMessageRef = useRef(onMessage)

  useEffect(() => {
    onMessageRef.current = onMessage
  }, [onMessage])

  useEffect(() => {
    shouldReconnectRef.current = true

    const buildUrl = (): string => {
      if (path.startsWith('ws://') || path.startsWith('wss://')) return path
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${proto}//${window.location.host}${path.startsWith('/') ? '' : '/'}${path}`
    }

    const connect = () => {
      setStatus('connecting')
      const ws = new WebSocket(buildUrl())
      wsRef.current = ws

      ws.onopen = () => setStatus('open')

      ws.onmessage = (event) => {
        let data: unknown = event.data
        if (typeof event.data === 'string') {
          try {
            data = JSON.parse(event.data)
          } catch {
            data = event.data
          }
        }
        setLastMessage(data)
        onMessageRef.current?.(data)
      }

      // NOTE: do NOT trigger reconnect here — onerror is always followed by onclose.
      ws.onerror = () => {
        // Intentionally empty. Status flip + reconnect happens in onclose.
      }

      ws.onclose = () => {
        setStatus('closed')
        if (!shouldReconnectRef.current) return
        reconnectTimerRef.current = window.setTimeout(connect, reconnectDelayMs)
      }
    }

    connect()

    return () => {
      shouldReconnectRef.current = false
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      const ws = wsRef.current
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        ws.close()
      }
      wsRef.current = null
    }
  }, [path, reconnectDelayMs])

  const send = (payload: unknown): boolean => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return false
    const data = typeof payload === 'string' ? payload : JSON.stringify(payload)
    ws.send(data)
    return true
  }

  return { status, lastMessage, send }
}
