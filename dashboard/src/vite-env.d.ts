/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_GOOGLE_CLIENT_ID?: string;
  readonly VITE_APP_NAME?: string;
  readonly VITE_SUPPORT_EMAIL?: string;
  readonly VITE_EXTENSION_DOWNLOAD_URL?: string;
  readonly VITE_ENABLE_DEV_LOGIN?: string;
  readonly VITE_SENTRY_DSN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}