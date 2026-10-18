<script>
  let { color, to, minutes, unit } = $props();
</script>

{#key to?.fr}
  <div class="board">
    <span class="badge-dot" style:background={color}></span>
    <div class="dest">
      <p class="fr" lang="fr">{to?.fr ?? ''}</p>
      <p class="ar" lang="ar" dir="rtl">{to?.ar ?? ''}</p>
    </div>
    <p class="eta"><strong>{minutes ?? ''}</strong> {unit}</p>
  </div>
{/key}

<style>
  .board {
    position: relative; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 14px;
    padding: 16px 18px; border-radius: 14px; background: #0a0a0a; color: var(--amber);
    text-shadow: 0 0 10px rgb(244 180 0 / 0.45); transform-origin: top;
    animation: flip 0.45s cubic-bezier(0.2, 0.7, 0.2, 1);
  }
  /* LED-matrix grid laid over the lettering */
  .board::after {
    content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    background: radial-gradient(circle, #0a0a0a 28%, transparent 31%) 0 0 / 3px 3px;
  }
  .badge-dot {
    width: 18px; height: 18px; border-radius: 50%; flex-shrink: 0;
    position: relative; z-index: 1; border: 3px solid #fff;
    box-shadow: 0 0 6px rgb(0 0 0 / 0.4);
  }
  .dest p { margin: 0; }
  .fr { font-size: 1.35rem; font-weight: 700; line-height: 1.2; }
  .ar { font-size: 1.5rem; font-weight: 600; line-height: 1.3; }
  .eta { margin: 0; text-align: end; font-size: 0.9rem; }
  .eta strong { display: block; font-size: 2rem; line-height: 1; font-variant-numeric: tabular-nums; }
  @keyframes flip { from { transform: rotateX(-80deg); opacity: 0.2; } to { transform: none; opacity: 1; } }
</style>
