<!--
  BOARD COMPONENT  –  amber LED destination board (used in +page.svelte, section 2c)
  Shows: line badge | destination in French + Arabic | trip duration
-->

<script>
  // Values passed in by the page: badge text/color, destination place, minutes, and the "min" label
  let { badge, color, to, minutes, unit } = $props();
</script>

<!-- {#key}: re-creates the board whenever the route or destination changes, which replays the flip animation -->
{#key badge + to.fr}
  <div class="board">
    <!-- Left: colored line badge (TGM / Bus) -->
    <span class="badge" style:background={color}>{badge}</span>
    <!-- Middle: destination name, French on top, Arabic below -->
    <div class="dest">
      <p class="fr" lang="fr">{to.fr}</p>
      <p class="ar" lang="ar" dir="rtl">{to.ar}</p>
    </div>
    <!-- Right: big trip duration number + unit -->
    <p class="eta"><strong>{minutes}</strong> {unit}</p>
  </div>
{/key}

<style>
  /* Black rounded box with amber glowing text */
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
  /* Colored line badge (sits above the LED dot pattern) */
  .badge {
    min-width: 52px; padding: 6px 10px; border-radius: 8px; text-align: center;
    position: relative; z-index: 1; color: #fff; font-weight: 700; text-shadow: none;
  }
  /* Destination text */
  .dest p { margin: 0; }
  .fr { font-size: 1.35rem; font-weight: 700; line-height: 1.2; }
  .ar { font-size: 1.5rem; font-weight: 600; line-height: 1.3; }
  /* Duration block on the right */
  .eta { margin: 0; text-align: end; font-size: 0.9rem; }
  .eta strong { display: block; font-size: 2rem; line-height: 1; font-variant-numeric: tabular-nums; }
  /* Flip-in animation, like an old departure board changing */
  @keyframes flip { from { transform: rotateX(-80deg); opacity: 0.2; } to { transform: none; opacity: 1; } }
</style>
