// Typed fetch wrapper for the Riven Scanner backend.
// Honors VITE_API_BASE for non-dev deploys; in dev the Vite proxy handles `/api`.

const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`
  const headers: HeadersInit = {
    accept: 'application/json',
    ...(init?.body ? { 'content-type': 'application/json' } : {}),
    ...init?.headers,
  }

  const res = await fetch(url, { ...init, headers })

  let body: unknown = null
  const text = await res.text()
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  if (!res.ok) {
    throw new ApiError(
      `API ${res.status} on ${path}`,
      res.status,
      body,
    )
  }

  return body as T
}
