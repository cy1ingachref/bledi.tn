<script lang="ts">
  import Icon from "$lib/ui/Icon.svelte";
  import Section from "$lib/ui/Section.svelte";
  import { modeLabel, type Translate } from "$lib/application/i18n";
  import type { Objective } from "$lib/domain/transit";
  import type { ModeChip } from "$lib/ui/modeStyle";

  const OBJECTIVES: { id: Objective; icon: string }[] = [
    { id: "fastest", icon: "clock" },
    { id: "cheapest", icon: "coin" },
    { id: "fewest_transfers", icon: "transfer" },
  ];

  let {
    t,
    chips,
    selected,
    unclassifiedCount,
    objective = $bindable(),
    showRoads = $bindable(),
    showRails = $bindable(),
    showUnclassified = $bindable(),
    onToggleMode,
    onSetAll,
  }: {
    t: Translate;
    chips: ModeChip[];
    selected: Set<string>;
    unclassifiedCount: number;
    objective: Objective;
    showRoads: boolean;
    showRails: boolean;
    showUnclassified: boolean;
    onToggleMode: (id: string) => void;
    onSetAll: (on: boolean) => void;
  } = $props();

  const count = $derived(selected.size);
</script>

<Section title={t("priority.title")}>
  <div class="seg" role="group" aria-label={t("priority.title")}>
    <span
      class="seg-pill"
      aria-hidden="true"
      style="transform:translateX({OBJECTIVES.findIndex((o) => o.id === objective) * 100}%)"
    ></span>
    {#each OBJECTIVES as o (o.id)}
      <button
        class="seg-btn"
        class:on={objective === o.id}
        onclick={() => (objective = o.id)}
        aria-pressed={objective === o.id}
      >
        <Icon name={o.icon} size={13} />
        <span>{t("priority." + o.id)}</span>
      </button>
    {/each}
  </div>
</Section>

<Section title={t("modes.title")}>
  {#snippet titleExtra()}
    <span class="counter" class:zero={count === 0}>{count}/{chips.length}</span>
  {/snippet}
  {#snippet aside()}
    <span class="mini-actions">
      <button class="mini" onclick={() => onSetAll(true)}>{t("modes.selectAll")}</button>
      <span class="sep">·</span>
      <button class="mini" onclick={() => onSetAll(false)}>{t("modes.clear")}</button>
    </span>
  {/snippet}
  <div class="modes">
    {#each chips as m (m.id)}
      {@const on = selected.has(m.id)}
      <button
        class="mode"
        class:on
        onclick={() => onToggleMode(m.id)}
        aria-pressed={on}
        style={on ? `--mc:${m.color}` : ""}
      >
        <span class="m-ic"><Icon name={m.icon} size={14} /></span>
        <span class="m-lbl">{modeLabel(t, m.id)}</span>
        <span class="m-n">{m.count.toLocaleString()}</span>
      </button>
    {/each}
  </div>
  {#if count === 0}
    <p class="hint-warn" role="status">
      <Icon name="alert" size={13} /> {t("error.noModes")}
    </p>
  {/if}
</Section>

<Section title={t("legend.network")}>
  <div class="layers">
    <button class="layer" class:on={showRoads} onclick={() => (showRoads = !showRoads)} aria-pressed={showRoads}>
      <span class="ly-line road" aria-hidden="true"></span>
      <span class="ly-tx">{t("modes.bus")}</span>
      <Icon name={showRoads ? "eye" : "eyeOff"} size={13} />
    </button>
    <button class="layer" class:on={showRails} onclick={() => (showRails = !showRails)} aria-pressed={showRails}>
      <span class="ly-line rail" aria-hidden="true"></span>
      <span class="ly-tx">{t("modes.train")}</span>
      <Icon name={showRails ? "eye" : "eyeOff"} size={13} />
    </button>
    {#if unclassifiedCount > 0}
      <button
        class="layer"
        class:on={showUnclassified}
        onclick={() => (showUnclassified = !showUnclassified)}
        aria-pressed={showUnclassified}
      >
        <span class="ly-line unk" aria-hidden="true"></span>
        <span class="ly-tx">{t("modes.unclassified")}</span>
        <span class="m-n">{unclassifiedCount}</span>
      </button>
    {/if}
  </div>
</Section>

<style>
  .counter {
    padding: 2px 8px;
    border: 1px solid var(--line);
    border-radius: 99px;
    background: rgba(61, 242, 201, 0.1);
    color: var(--glow);
    font-size: 10px; font-weight: 700;
    letter-spacing: 0;
    font-variant-numeric: tabular-nums;
  }
  .counter.zero { border-color: rgba(255, 61, 129, 0.45); background: rgba(255, 61, 129, 0.12); color: #ff8fb3; }

  .mini-actions { display: inline-flex; align-items: center; gap: 4px; }
  .mini {
    border: 0; background: none; padding: 2px 5px;
    color: var(--mu); font: inherit; font-size: 11px; font-weight: 600;
    cursor: pointer; border-radius: 6px;
    transition: color 0.25s ease;
  }
  .mini:hover { color: var(--a1); }
  .sep { color: var(--line); }

  .seg {
    position: relative;
    display: grid; grid-template-columns: repeat(3, 1fr);
    background: rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 4px;
  }
  .seg-pill {
    position: absolute; top: 4px; bottom: 4px; left: 4px;
    width: calc(33.333% - 2.7px);
    border-radius: 12px;
    background: linear-gradient(135deg, var(--a1), var(--a2));
    box-shadow: 0 0 18px rgba(123, 92, 255, 0.4);
    transition: transform 0.45s cubic-bezier(.3,1.4,.4,1);
    pointer-events: none;
  }
  .seg-btn {
    position: relative; z-index: 1;
    display: flex; align-items: center; justify-content: center; gap: 5px;
    background: none; border: 0;
    color: var(--mu);
    padding: 10px 4px;
    font: 600 11.5px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: color 0.3s ease;
  }
  .seg-btn.on { color: var(--on-accent); }

  .modes { display: flex; gap: 8px; flex-wrap: wrap; }
  .mode {
    --mc: var(--mu);
    display: flex; align-items: center; gap: 7px;
    padding: 8px 11px;
    border-radius: 14px;
    border: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.03);
    color: var(--mu);
    cursor: pointer;
    font: 600 12.5px "DM Sans", system-ui, sans-serif;
    transition: all 0.3s ease;
  }
  .mode:hover { border-color: rgba(200, 180, 255, 0.28); }
  .m-ic { display: grid; place-items: center; flex-shrink: 0; color: var(--mu-2); transition: color 0.3s ease; }
  .m-lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .m-n {
    font-size: 10px; font-weight: 700; color: var(--mu-2);
    font-variant-numeric: tabular-nums;
    padding: 1px 5px; border-radius: 6px; background: rgba(255, 255, 255, 0.05);
  }
  .mode.on {
    color: var(--tx);
    border-color: var(--mc);
    background: color-mix(in srgb, var(--mc) 16%, transparent);
    box-shadow: 0 0 16px color-mix(in srgb, var(--mc) 34%, transparent),
                inset 0 0 12px color-mix(in srgb, var(--mc) 12%, transparent);
  }
  .mode.on .m-ic { color: var(--mc); filter: drop-shadow(0 0 5px var(--mc)); }
  .mode.on .m-n { color: var(--mc); background: color-mix(in srgb, var(--mc) 16%, transparent); }

  .layers { display: flex; flex-wrap: wrap; gap: 8px; }
  .layer {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 7px 11px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surf-2);
    color: var(--mu);
    font: 600 11.5px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .layer:hover { border-color: rgba(200, 180, 255, 0.3); color: var(--tx); }
  .layer.on { color: var(--tx); border-color: rgba(200, 180, 255, 0.35); background: rgba(255, 255, 255, 0.06); }
  .layer :global(svg) { color: var(--mu-2); }
  .layer.on :global(svg) { color: var(--glow); }
  .ly-tx { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ly-line { width: 18px; height: 3px; border-radius: 3px; flex-shrink: 0; }
  .ly-line.road { background: linear-gradient(90deg, var(--n-bus), var(--n-louaj)); box-shadow: 0 0 8px var(--n-bus); }
  .ly-line.rail { background: linear-gradient(90deg, var(--n-metro), var(--n-train)); box-shadow: 0 0 8px var(--n-train); }
  .ly-line.unk { background: repeating-linear-gradient(90deg, var(--n-unk) 0 4px, transparent 4px 7px); }

  .hint-warn {
    display: flex; align-items: center; gap: 6px;
    margin: 0; padding: 8px 11px;
    border: 1px solid rgba(255, 196, 0, 0.3);
    border-radius: 12px;
    background: rgba(255, 196, 0, 0.1);
    color: #ffd98a;
    font-size: 11.5px;
  }
</style>
