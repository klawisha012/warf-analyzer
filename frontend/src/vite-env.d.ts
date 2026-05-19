/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Override the API base URL (e.g. http://backend:8000). Optional; empty in dev when using Vite proxy. */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
