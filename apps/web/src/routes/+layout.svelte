<script lang="ts">
  import { onMount } from "svelte";
  import { provideServices } from "$lib/app/services";
  import "../app.css";

  let { children } = $props();

  provideServices();

  // Service worker registration. SvelteKit's adapter-static writes index.html
  // AFTER vite-plugin-pwa's HTML transform runs, so the plugin's injected
  // <script src="registerSW.js"> never lands and the worker was silently never
  // registered. Registering from the layout is the SvelteKit-native path.
  onMount(async () => {
    if (!("serviceWorker" in navigator)) return;
    try {
      const { registerSW } = await import("virtual:pwa-register");
      registerSW({ immediate: true });
    } catch (e) {
      console.warn("PWA registration failed:", e);
    }
  });
</script>

{@render children()}
