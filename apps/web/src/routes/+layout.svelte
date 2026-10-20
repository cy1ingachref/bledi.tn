<script>
  import '@fontsource-variable/readex-pro';
  import '../app.css';
  import { ui } from '$lib/ui.svelte.js';
  let { children } = $props();

  $effect(() => {
    document.documentElement.lang = ui.lang;
    document.documentElement.dir = ui.lang === 'ar' ? 'rtl' : 'ltr';
  });
</script>

<svelte:head><title>bledi.tn</title></svelte:head>
{@render children()}
