<script lang="ts">
  import { modeLabel, type Translate } from "$lib/application/i18n";
  import type { ModeChip } from "$lib/ui/modeStyle";

  let { t, chips, selected }: { t: Translate; chips: ModeChip[]; selected: Set<string> } = $props();
</script>

<div class="legend">
  <div class="lg-grid">
    {#each chips as m (m.id)}
      <span class="lg-i" class:off={!selected.has(m.id)}>
        <i style="background:{m.color}"></i>{modeLabel(t, m.id)}
      </span>
    {/each}
  </div>
</div>

<style>
  .legend {
    position: absolute;
    bottom: 16px; inset-inline-start: 16px;
    z-index: 700;
    padding: 8px 12px;
    border: 1px solid var(--line);
    border-radius: 99px;
    background: var(--surf);
    backdrop-filter: blur(16px);
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.6);
    max-width: min(340px, calc(100% - 32px));
  }
  .lg-grid { display: flex; flex-wrap: wrap; gap: 6px 14px; }
  .lg-i {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: var(--mu);
    transition: opacity 0.3s ease;
  }
  .lg-i i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 6px currentColor; }
  .lg-i.off { opacity: 0.32; text-decoration: line-through; }

  @media (max-width: 900px) {
    .legend { display: none; }
  }
</style>
