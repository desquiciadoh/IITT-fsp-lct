/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_MOCKS?: 'all' | 'missing' | 'off'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
