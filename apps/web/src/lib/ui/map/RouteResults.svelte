<script lang="ts">
  import Icon from "$lib/ui/Icon.svelte";
  import Section from "$lib/ui/Section.svelte";
  import Alert from "$lib/ui/Alert.svelte";
  import { modeColor, modeIcon } from "$lib/ui/modeStyle";
  import { formatDuration, legLabel, modeLabelFor, type Translate } from "$lib/application/i18n";
  import { fareOf, isWalkLeg, mergeLegs } from "$lib/domain/itinerary";
  import { uniqueModes } from "$lib/domain/modes";
  import type { RouteLeg, RoutePlan } from "$lib/domain/transit";

  let {
    t,
    plan,
    selectedIndex,
    focused,
    el = $bindable(null),
    onSelect,
    onToggleFocus,
  }: {
    t: Translate;
    plan: RoutePlan;
    selectedIndex: number;
    focused: boolean;
    el?: HTMLElement | null;
    onSelect: (index: number) => void;
    onToggleFocus: () => void;
  } = $props();

  /** Steps for the selected itinerary, with same-line hops collapsed. */
  const steps = $derived.by(() => {
    const itin = plan.itineraries?.[selectedIndex];
    return itin ? mergeLegs(itin.legs ?? []) : [];
  });

  function legColor(leg: RouteLeg): string {
    return isWalkLeg(leg) ? "#8b83a8" : modeColor(leg.mode ?? "bus");
  }
</script>

{#if plan.itineraries?.length}
  <Section title={t("results.title")} bind:el>
    {#snippet aside()}
      <span class="sub">{t("results.subtitle")}</span>
    {/snippet}

    {#each plan.itineraries as itin, i}
      {@const fare = fareOf(itin)}
      <button
        class="itin"
        class:on={selectedIndex === i}
        onclick={() => onSelect(i)}
        aria-pressed={selectedIndex === i}
      >
        <div class="it-top">
          <span class="it-n">{t("results.option")} {i + 1}</span>
          <span class="it-dur">{formatDuration(itin.duration_min, t)}</span>
        </div>
        <div class="it-fare">
          {#if fare > 0}<span class="it-price">{fare.toFixed(2)} DT</span>{/if}
          <span class="it-mode">
            {uniqueModes(itin.modes_used).map((mu) => modeLabelFor(t, mu)).join(" + ")}
          </span>
        </div>
        <!-- Leg bar: one neon segment per transport type. -->
        <div class="legs" aria-hidden="true">
          {#each uniqueModes(itin.modes_used) as mu}
            <span class="leg" style="--c:{modeColor(mu)}"></span>
          {/each}
        </div>
        <div class="it-meta">
          <span>
            <Icon name="transfer" size={12} />
            {itin.transfers === 0
              ? t("results.direct")
              : `${itin.transfers} ${t(itin.transfers > 1 ? "results.transfersPlural" : "results.transfers")}`}
          </span>
          {#if i === 0}<span class="tag">{t("results.best")}</span>{/if}
        </div>
        {#if selectedIndex === i && steps.length > 0}
          <ol class="steps">
            {#each steps as leg}
              <li class="step" style="--c:{legColor(leg)}">
                <span class="s-ic">
                  <Icon
                    name={isWalkLeg(leg) ? "walk" : modeIcon(leg.mode ?? "bus")}
                    size={12}
                  />
                </span>
                <span class="s-tx">{legLabel(t, leg)}</span>
                {#if leg.duration_min}<span class="s-d">{Math.round(leg.duration_min)}′</span>{/if}
              </li>
            {/each}
          </ol>
        {/if}
      </button>
    {/each}

    <!-- Focus control: show the route alone, or bring the whole
         network back. The rider decides; the default is the route. -->
    <button
      class="focus-btn"
      class:on={focused}
      onclick={onToggleFocus}
      aria-pressed={focused}
    >
      <Icon name={focused ? "eyeOff" : "network"} size={14} />
      {focused ? t("results.showNetwork") : t("results.hideNetwork")}
    </button>
    {#if focused}
      <p class="focus-note" role="status">
        <Icon name="info" size={12} /> {t("results.focused")}
      </p>
    {/if}
  </Section>
{:else}
  <Alert message={t("results.none")} warn />
{/if}

<style>
  .sub { font-size: 10px; color: var(--mu-2); }

  .itin {
    display: flex; flex-direction: column; gap: 8px;
    width: 100%; padding: 14px;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--surf-2);
    color: inherit;
    font: inherit; text-align: start;
    cursor: pointer;
    transition: all 0.3s ease;
  }
  .itin:hover { border-color: rgba(200, 180, 255, 0.28); transform: translateX(3px); }
  .itin.on {
    border-color: var(--glow);
    background: rgba(61, 242, 201, 0.06);
    box-shadow: 0 0 22px rgba(61, 242, 201, 0.16);
    transform: translateX(4px);
  }
  .it-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  .it-n { font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mu-2); }
  .it-dur {
    font-family: "Sora", system-ui, sans-serif;
    font-size: 22px; font-weight: 700; color: var(--tx);
    font-variant-numeric: tabular-nums; letter-spacing: -0.4px;
  }
  .itin.on .it-dur { color: var(--glow); }

  .it-fare { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .it-price { font-size: 13px; font-weight: 700; color: var(--a1); font-variant-numeric: tabular-nums; }
  .it-mode { font-size: 11.5px; color: var(--mu); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .legs { display: flex; align-items: center; gap: 4px; }
  .leg {
    height: 8px; border-radius: 9px; flex: 1 1 0;
    background: var(--c);
    box-shadow: 0 0 10px color-mix(in srgb, var(--c) 70%, transparent);
    transform-origin: left;
    animation: grow 0.7s cubic-bezier(.2,.9,.2,1) both;
  }
  @keyframes grow { from { transform: scaleX(0); } }

  .it-meta { display: flex; align-items: center; gap: 10px; color: var(--mu); font-size: 11.5px; }
  .it-meta span { display: inline-flex; align-items: center; gap: 4px; }
  .tag {
    font-size: 10.5px; font-weight: 700;
    padding: 3px 9px;
    border-radius: 99px;
    background: rgba(61, 242, 201, 0.14);
    color: var(--glow);
    margin-inline-start: auto;
  }

  .steps {
    list-style: none; margin: 3px 0 0; padding: 9px 0 0;
    border-top: 1px dashed rgba(200, 180, 255, 0.16);
    display: flex; flex-direction: column; gap: 7px;
  }
  .step { display: flex; align-items: center; gap: 9px; font-size: 11.5px; color: var(--mu); }
  .s-ic {
    display: grid; place-items: center;
    width: 22px; height: 22px; flex-shrink: 0;
    border-radius: 7px;
    background: color-mix(in srgb, var(--c) 20%, transparent);
    color: var(--c);
  }
  .s-tx { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .s-d { color: var(--mu-2); font-variant-numeric: tabular-nums; }

  .focus-btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; padding: 11px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: var(--surf-2);
    color: var(--mu);
    font: 600 12px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .focus-btn:hover { border-color: var(--a1); color: var(--tx); }
  .focus-btn.on { border-color: var(--glow); color: var(--glow); background: rgba(61, 242, 201, 0.08); }
  .focus-note {
    display: flex; align-items: center; gap: 6px;
    margin: 0; font-size: 11px; color: var(--mu-2);
  }
</style>
