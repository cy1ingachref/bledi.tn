<script lang="ts">
  import Icon from "$lib/ui/Icon.svelte";
  import Section from "$lib/ui/Section.svelte";
  import Spinner from "$lib/ui/Spinner.svelte";
  import EndpointBadge from "$lib/ui/EndpointBadge.svelte";
  import { useTransit } from "$lib/ui/context";
  import { modeLabelFor, type Translate } from "$lib/application/i18n";
  import type { Endpoint, PlaceHit } from "$lib/domain/transit";

  let {
    t,
    shownStops,
    pickMode,
    from,
    to,
    locating,
    onStartPick,
    onPick,
    onSwap,
    onLocate,
  }: {
    t: Translate;
    shownStops: number;
    pickMode: "from" | "to" | null;
    from: Endpoint | null;
    to: Endpoint | null;
    locating: boolean;
    onStartPick: (which: "from" | "to") => void;
    onPick: (hit: PlaceHit) => void;
    onSwap: () => void;
    onLocate: () => void;
  } = $props();

  const transit = useTransit();

  let query = $state("");
  let hits = $state<PlaceHit[]>([]);
  let searching = $state(false);
  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  // Responses can arrive out of order; only the latest search, if not superseded by a pick,
  // may write the hits.
  let searchSeq = 0;

  function runSearch() {
    const seq = ++searchSeq;
    const q = query.trim();
    if (q.length < 2) { hits = []; searching = false; return; }
    searching = true;
    transit
      .searchPlaces(q, from ? { lat: from.lat, lon: from.lon } : null)
      .then((r) => { if (seq === searchSeq) hits = r; })
      .catch(() => { if (seq === searchSeq) hits = []; })
      .finally(() => { if (seq === searchSeq) searching = false; });
  }

  function onQueryInput() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 300);
  }

  function pick(h: PlaceHit) {
    onPick(h);
    searchSeq++;
    if (searchTimer) clearTimeout(searchTimer);
    hits = [];
    query = "";
    searching = false;
  }
</script>

<Section title={t("search.usePlace")}>
  {#snippet aside()}
    <span class="mini-actions">
      <span class="count-pill">{shownStops} {t("status.stops")}</span>
    </span>
  {/snippet}

  <div class="search-row" class:active={!!pickMode}>
    <Icon name="search" size={15} cls="s-ic" />
    <input
      bind:value={query}
      oninput={onQueryInput}
      placeholder={t("search.placeholder")}
      aria-label={t("search.placeholder")}
    />
    {#if searching}<Spinner />{/if}
  </div>

  <div class="targets" role="group" aria-label={t("search.usePlace")}>
    <button
      class="tgt" class:on={pickMode === "from"}
      onclick={() => onStartPick("from")}
      aria-pressed={pickMode === "from"}
    >
      <EndpointBadge end="a" />{t("trip.from")}
      <Icon name="crosshair" size={12} cls="tgt-ic" />
    </button>
    <button
      class="tgt" class:on={pickMode === "to"}
      onclick={() => onStartPick("to")}
      aria-pressed={pickMode === "to"}
    >
      <EndpointBadge end="b" />{t("trip.to")}
      <Icon name="crosshair" size={12} cls="tgt-ic" />
    </button>
  </div>

  {#if pickMode}
    <p class="pick-note" role="status">
      <Icon name="crosshair" size={12} /> {t("trip.pickHint")}
    </p>
  {/if}

  {#if hits.length > 0}
    <ul class="hits">
      {#each hits as h}
        <li>
          <button class="hit" onclick={() => pick(h)}>
            <span class="hit-ic" style="--c:{h.kind === 'city' ? '#ffc400' : '#ff3d81'}">
              <Icon name={h.kind === "city" ? "pin" : "target"} size={12} />
            </span>
            <span class="hit-tx">
              <b>{h.name}</b>
              <small>
                {h.city}
                {#if h.modes.length}· {h.modes.map((m) => modeLabelFor(t, m)).join(", ")}{/if}
              </small>
            </span>
            <Icon name="arrowRight" size={13} cls="hit-go" />
          </button>
        </li>
      {/each}
    </ul>
  {:else if query.trim().length >= 2 && !searching}
    <p class="no-hit">{t("search.noResults")}</p>
  {/if}

  <div class="trip">
    <div class="trip-row">
      <span class="pin a" aria-hidden="true"></span>
      <button class="trip-in" onclick={() => onStartPick("from")}>
        <span class="trip-lbl">{t("trip.from")}</span>
        <span class="trip-val" class:empty={!from}>
          {from ? from.name : t("trip.notSet")}
        </span>
      </button>
    </div>
    <div class="trip-row">
      <span class="pin b" aria-hidden="true"></span>
      <button class="trip-in" onclick={() => onStartPick("to")}>
        <span class="trip-lbl">{t("trip.to")}</span>
        <span class="trip-val" class:empty={!to}>
          {to ? to.name : t("trip.notSet")}
        </span>
      </button>
    </div>
    <button class="swap" onclick={onSwap} aria-label={t("trip.swap")} title={t("trip.swap")}>
      <Icon name="transfer" size={15} />
    </button>
  </div>

  <div class="quick">
    <button class="chip" onclick={onLocate} disabled={locating}>
      <Icon name="locate" size={13} />
      {locating ? t("trip.locating") : t("trip.myLocation")}
    </button>
    <button class="chip" onclick={() => onStartPick("from")}>
      <Icon name="crosshair" size={13} />
      {t("trip.pickOnMap")}
    </button>
  </div>
</Section>

<style>
  .mini-actions { display: inline-flex; align-items: center; gap: 4px; }
  .count-pill {
    font-size: 10px; font-weight: 600; color: var(--mu-2);
    padding: 2px 8px; border-radius: 99px; border: 1px solid var(--line);
    font-variant-numeric: tabular-nums;
  }

  .search-row {
    display: flex; align-items: center; gap: 9px;
    padding: 0 12px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--surf-2);
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
  }
  .search-row:focus-within { border-color: var(--a1); box-shadow: 0 0 0 3px rgba(255, 138, 212, 0.15); }
  .search-row.active { border-color: var(--glow); box-shadow: 0 0 0 3px rgba(61, 242, 201, 0.14); }
  .search-row :global(svg.s-ic) { color: var(--mu); flex-shrink: 0; }
  .search-row input {
    flex: 1; min-width: 0; min-height: 42px;
    border: 0; background: none; outline: none;
    color: var(--tx); font: inherit; font-size: 14px;
  }
  .search-row input::placeholder { color: var(--mu-2); }

  .targets { display: flex; gap: 6px; }
  .tgt {
    display: inline-flex; align-items: center; gap: 6px;
    flex: 1; min-height: 36px; padding: 5px 10px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surf-2);
    color: var(--mu);
    font: inherit; font-size: 11.5px; font-weight: 600;
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .tgt:hover { border-color: rgba(255, 138, 212, 0.45); color: var(--tx); }
  .tgt.on { border-color: var(--glow); background: rgba(61, 242, 201, 0.1); color: var(--glow); }
  .tgt :global(svg.tgt-ic) { margin-inline-start: auto; opacity: 0.6; }
  .tgt.on :global(svg.tgt-ic) { opacity: 1; }

  .pick-note {
    display: flex; align-items: center; gap: 6px;
    margin: 0; padding: 7px 11px;
    border: 1px dashed rgba(61, 242, 201, 0.4);
    border-radius: 11px;
    background: rgba(61, 242, 201, 0.07);
    color: var(--glow);
    font-size: 11.5px;
  }

  .hits {
    list-style: none; margin: 0; padding: 5px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: var(--bg);
    display: flex; flex-direction: column; gap: 2px;
    max-height: 230px; overflow-y: auto;
  }
  .hit {
    display: flex; align-items: center; gap: 9px;
    width: 100%; padding: 8px 9px;
    border: 0; border-radius: 11px;
    background: none; color: var(--mu);
    font: inherit; font-size: 12.5px; text-align: start;
    cursor: pointer;
    transition: background 0.2s ease, color 0.2s ease;
  }
  .hit:hover { background: rgba(255, 138, 212, 0.1); color: var(--tx); }
  .hit-ic {
    display: grid; place-items: center;
    width: 24px; height: 24px; flex-shrink: 0;
    border-radius: 8px;
    background: color-mix(in srgb, var(--c) 20%, transparent);
    color: var(--c);
  }
  .hit-tx { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .hit-tx b { font-weight: 600; color: var(--tx); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hit-tx small { font-size: 10.5px; color: var(--mu-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .hit :global(svg.hit-go) { color: var(--mu-2); flex-shrink: 0; }
  .no-hit { margin: 0; padding: 2px 4px; color: var(--mu-2); font-size: 11.5px; }

  .trip {
    position: relative;
    background: var(--surf-2);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 6px 54px 6px 14px;
  }
  .trip::before {
    content: "";
    position: absolute;
    left: 20px; top: 34px; bottom: 34px;
    border-left: 2px dotted var(--mu-2);
  }
  .trip-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; position: relative; z-index: 1; }
  .trip-row + .trip-row { border-top: 1px solid var(--line); }
  .pin { width: 13px; height: 13px; border-radius: 50%; flex: none; }
  .pin.a { background: #22d3ee; box-shadow: 0 0 0 4px rgba(34, 211, 238, 0.2), 0 0 12px #22d3ee; }
  .pin.b { background: #f472b6; box-shadow: 0 0 0 4px rgba(244, 114, 182, 0.2), 0 0 12px #f472b6; }

  .trip-in {
    flex: 1; min-width: 0;
    display: flex; flex-direction: column; gap: 1px;
    border: 0; background: none; padding: 0;
    text-align: start; cursor: pointer; font: inherit;
  }
  .trip-lbl { font-size: 10px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mu-2); }
  .trip-val {
    font-size: 14px; font-weight: 500; color: var(--tx);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .trip-val.empty { color: var(--mu-2); font-style: italic; }

  .swap {
    position: absolute; right: 11px; top: 50%; translate: 0 -50%;
    width: 34px; height: 34px;
    display: grid; place-items: center;
    border-radius: 50%;
    border: 1px solid var(--line);
    background: var(--bg); color: var(--tx);
    cursor: pointer;
    transition: transform 0.4s cubic-bezier(.3,1.4,.4,1), border-color 0.3s ease;
  }
  .swap:hover { transform: rotate(180deg); border-color: var(--a1); color: var(--a1); }

  .quick { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip {
    display: inline-flex; align-items: center; gap: 6px;
    border: 1px solid var(--line);
    background: var(--surf-2);
    color: var(--tx);
    padding: 8px 13px;
    border-radius: 99px;
    font: 500 12.5px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: transform 0.25s ease, border-color 0.25s ease;
  }
  .chip:hover:not(:disabled) { border-color: var(--a1); transform: translateY(-2px); }
  .chip:disabled { opacity: 0.55; cursor: default; }
  .chip :global(svg) { color: var(--glow); }
</style>
