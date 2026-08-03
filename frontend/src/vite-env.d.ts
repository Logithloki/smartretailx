/// <reference types="vite/client" />

// Widen import.meta.env with the specific VITE_* keys the SPA reads.
// Any missing/misspelled key is caught by TypeScript at build time.
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_COGNITO_AUTHORITY: string;
  readonly VITE_COGNITO_CLIENT_ID: string;
  readonly VITE_COGNITO_REDIRECT_URI: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
