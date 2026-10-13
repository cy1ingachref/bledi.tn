<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    title,
    titleExtra,
    aside,
    el = $bindable(null),
    children,
  }: {
    title: string;
    titleExtra?: Snippet;
    aside?: Snippet;
    el?: HTMLElement | null;
    children: Snippet;
  } = $props();
</script>

{#snippet heading()}
  <h2>{title}{@render titleExtra?.()}</h2>
{/snippet}

<section class="sec" bind:this={el}>
  {#if aside}
    <div class="sec-head">
      {@render heading()}
      {@render aside()}
    </div>
  {:else}
    {@render heading()}
  {/if}
  {@render children()}
</section>

<style>
  .sec { display: flex; flex-direction: column; gap: 10px; }
  .sec-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  h2 {
    display: flex; align-items: center; gap: 6px;
    margin: 0;
    font-family: "Sora", system-ui, sans-serif;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--mu);
  }
</style>
