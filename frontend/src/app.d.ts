/// <reference types="@sveltejs/kit" />
/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

// `virtual:pwa-register` is provided by vite-plugin-pwa at build time; without
// this declaration svelte-check reports "Cannot find module" even though the
// build resolves it.
declare module "virtual:pwa-register" {
  export interface RegisterSWOptions {
    immediate?: boolean;
    onNeedRefresh?: () => void;
    onOfflineReady?: () => void;
    onRegistered?: (registration: ServiceWorkerRegistration | undefined) => void;
    onRegisterError?: (error: unknown) => void;
  }
  export function registerSW(options?: RegisterSWOptions): (reloadPage?: boolean) => Promise<void>;
}
