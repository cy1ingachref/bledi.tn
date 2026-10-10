/// <reference types="@sveltejs/kit" />
/// <reference types="vite-plugin-pwa/client" />

import { onMount } from 'svelte';

let updateSW: (reloadPage?: boolean) => Promise<void>;

onMount(async () => {
  if ('serviceWorker' in navigator) {
    try {
      const { registerSW } = await import('virtual:pwa-register');
      updateSW = registerSW({
        onNeedRefresh() {
          // Show "new content available" toast/button
          const shouldUpdate = confirm('New content available. Reload to update?');
          if (shouldUpdate) updateSW?.(true);
        },
        onOfflineReady() {
          console.log('App ready to work offline');
        }
      });
    } catch (e) {
      console.warn('PWA registration failed:', e);
    }
  }
});
