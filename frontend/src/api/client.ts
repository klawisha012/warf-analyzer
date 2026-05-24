/** Thin fetch wrapper. Backend lives under /api (rewritten to backend root by Vite/nginx). */

export class ApiError extends Error {
  constructor(public status: number, public detail: string, public path: string) {
    super(`API ${status} on ${path}: ${detail}`);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith("/api") ? path : `/api${path.startsWith("/") ? "" : "/"}${path}`;
  const res = await fetch(url, {
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      detail = JSON.parse(text).detail ?? text;
    } catch {
      /* keep raw */
    }
    throw new ApiError(res.status, detail, url);
  }
  return text ? (JSON.parse(text) as T) : (undefined as T);
}
