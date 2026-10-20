<script>
  import { ui } from '$lib/ui.svelte.js';
</script>

<div class="langs" role="group" aria-label="Language">
  {#each [['fr', 'FR'], ['ar', 'ع'], ['en', 'EN']] as [code, label]}
    <button aria-pressed={ui.lang === code} onclick={() => (ui.lang = code)}>{label}</button>
  {/each}
</div>

<style>
  .langs { display: flex; gap: 4px; }
  button { min-width: 40px; height: 36px; border: 1px solid #ffffff40; border-radius: 10px; background: transparent; color: #dfeaf0; }
  button[aria-pressed='true'] { background: #c9dde6; color: #0f2230; border-color: #c9dde6; }
</style>
