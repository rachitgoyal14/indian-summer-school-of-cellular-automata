/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_WS_URL?: string;
  // Add other VITE_ prefixed env vars here as needed
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
