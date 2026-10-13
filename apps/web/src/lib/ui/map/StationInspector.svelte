<script lang="ts">
  import Icon from "$lib/ui/Icon.svelte";
  import Alert from "$lib/ui/Alert.svelte";
  import Spinner from "$lib/ui/Spinner.svelte";
  import EndpointBadge from "$lib/ui/EndpointBadge.svelte";
  import { modeColor, modeIcon } from "$lib/ui/modeStyle";
  import { modeLabelFor, type Translate } from "$lib/application/i18n";
  import { louageDestinations } from "$lib/application/mapData";
  import type { Endpoint, LouageLink, StationDetail } from "$lib/domain/transit";

  let {
    t,
    station,
    loading,
    error,
    louageLinks,
    onClose,
    onSetEndpoint,
    onFocusStation,
  }: {
    t: Translate;
    station: StationDetail | null;
    loading: boolean;
    error: string;
    louageLinks: LouageLink[];
    onClose: () => void;
    onSetEndpoint: (which: "from" | "to", ep: Endpoint) => void;
    onFocusStation: (id: string, name: string) => void;
  } = $props();

  const destinations = $derived(station ? louageDestinations(louageLinks, station.id) : []);

  function setEndpoint(which: "from" | "to") {
    if (station?.lat && station?.lon)
      onSetEndpoint(which, {
        kind: "stop", id: station.id, name: station.name ?? "",
        lat: station.lat, lon: station.lon, modes: station.modes,
      });
  }
</script>

<!-- What actually calls at this stop: every line, the direction it runs in,
     and whether it starts, ends or passes here. -->
<aside class="inspector" aria-live="polite">
  <div class="ins-head">
    <div class="ins-title">
      <span class="ins-eyebrow">{t("station.title")}</span>
      <h3>{station?.name ?? ""}</h3>
      {#if station?.city}<span class="ins-city">{station.city}</span>{/if}
    </div>
    <button class="ins-close" onclick={onClose} aria-label={t("results.steps")}>
      <Icon name="close" size={15} />
    </button>
  </div>

  {#if loading}
    <p class="ins-loading"><Spinner /> {t("loading.station")}</p>
  {:else if error}
    <Alert message={error} size={14} />
  {:else if station}
    <div class="ins-modes">
      {#if station.modes.length}
        {#each station.modes as m}
          <span class="ins-mode" style="--c:{modeColor(m)}">
            <Icon name={modeIcon(m)} size={12} />{modeLabelFor(t, m)}
          </span>
        {/each}
      {:else}
        <span class="ins-mode none"><Icon name="pin" size={12} />{t("modes.unclassified")}</span>
      {/if}
      <span class="ins-count">{station.count} {t("station.count")}</span>
    </div>

    <div class="ins-actions">
      <button class="ins-act" onclick={() => setEndpoint("from")} disabled={!station.lat}>
        <EndpointBadge end="a" />{t("station.setFrom")}
      </button>
      <button class="ins-act" onclick={() => setEndpoint("to")} disabled={!station.lat}>
        <EndpointBadge end="b" />{t("station.setTo")}
      </button>
    </div>

    <h4>{t("station.lines")}</h4>
    {#if station.lines.length}
      <ul class="lines">
        {#each station.lines as ln}
          <li class="line" style="--c:{modeColor(ln.mode)}">
            <span class="ln-ic"><Icon name={modeIcon(ln.mode)} size={13} /></span>
            <span class="ln-body">
              <span class="ln-top">
                <b>{modeLabelFor(t, ln.mode)}{ln.number ? ` ${ln.number}` : ""}</b>
                <span class="ln-role">
                  {ln.role === "origin"
                    ? t("station.from")
                    : ln.role === "terminus"
                      ? t("station.to")
                      : t("station.through")}
                </span>
              </span>
              {#if ln.direction}<span class="ln-dir">{ln.direction}</span>{/if}
              <span class="ln-meta">
                {#if ln.operator}{ln.operator} · {/if}{ln.stops_count} {t("status.stops")}
              </span>
            </span>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="ins-none">
        {station.lines_known ? t("station.none") : t("station.unlisted")}
      </p>
    {/if}

    {#if destinations.length}
      <h4 class="ins-sub">{t("station.louage_links")}</h4>
      <ul class="ins-lines">
        {#each destinations as l}
          <li>
            <button
              class="ln-btn"
              onclick={() => onFocusStation(l.to, l.to_name)}
              title={l.destination_raw}
            >
              <span class="ln-top">
                <b>{l.to_name}</b>
                <span class="ln-role">{t("station.serves")}</span>
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</aside>

<style>
  .inspector {
    position: absolute;
    top: 16px; inset-inline-end: 16px;
    width: min(340px, calc(100% - 32px));
    max-height: calc(100% - 32px);
    overflow-y: auto;
    z-index: 720;
    padding: 15px;
    border: 1px solid var(--line);
    border-radius: 20px;
    background: var(--surf);
    backdrop-filter: blur(22px) saturate(1.4);
    box-shadow: 0 0 30px rgba(123, 92, 255, 0.18), 0 18px 50px rgba(0, 0, 0, 0.65);
    display: flex; flex-direction: column; gap: 12px;
    animation: slideIn 0.32s cubic-bezier(.2,.9,.2,1);
  }
  @keyframes slideIn { from { opacity: 0; transform: translateY(-10px); } }

  h4 {
    margin: 0;
    font-size: 11px; font-weight: 600;
    letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--mu-2);
  }

  .ins-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
  .ins-title { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .ins-eyebrow { font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--glow); }
  .ins-title h3 { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: -0.2px; }
  .ins-city { font-size: 11.5px; color: var(--mu); }
  .ins-close {
    display: grid; place-items: center;
    width: 30px; height: 30px; flex-shrink: 0;
    border-radius: 50%;
    border: 1px solid var(--line);
    background: var(--surf-2); color: var(--mu);
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .ins-close:hover { border-color: var(--a1); color: var(--a1); transform: rotate(90deg); }
  .ins-loading { display: flex; align-items: center; gap: 8px; margin: 0; color: var(--mu); font-size: 12px; }

  .ins-modes { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .ins-mode {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 9px;
    border-radius: 99px;
    border: 1px solid color-mix(in srgb, var(--c) 45%, transparent);
    background: color-mix(in srgb, var(--c) 14%, transparent);
    color: var(--c);
    font-size: 11px; font-weight: 600;
  }
  .ins-mode.none { --c: var(--n-unk); }
  .ins-count { margin-inline-start: auto; font-size: 10.5px; color: var(--mu-2); font-variant-numeric: tabular-nums; }

  .ins-actions { display: flex; gap: 7px; }
  .ins-act {
    display: inline-flex; align-items: center; gap: 6px;
    flex: 1; justify-content: center;
    padding: 9px 8px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surf-2);
    color: var(--tx);
    font: 600 11.5px "DM Sans", system-ui, sans-serif;
    cursor: pointer;
    transition: all 0.25s ease;
  }
  .ins-act:hover:not(:disabled) { border-color: var(--glow); color: var(--glow); }
  .ins-act:disabled { opacity: 0.45; cursor: not-allowed; }

  .lines { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 7px; }
  .line {
    display: flex; gap: 9px;
    padding: 9px;
    border: 1px solid var(--line);
    border-inline-start: 3px solid var(--c);
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.025);
  }
  .ln-ic {
    display: grid; place-items: center;
    width: 24px; height: 24px; flex-shrink: 0;
    border-radius: 8px;
    background: color-mix(in srgb, var(--c) 18%, transparent);
    color: var(--c);
  }
  .ln-body { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
  .ln-top { display: flex; align-items: baseline; gap: 7px; flex-wrap: wrap; }
  .ln-top b { font-size: 12.5px; color: var(--tx); }
  .ln-role { font-size: 10px; font-weight: 600; color: var(--c); }
  .ln-dir { font-size: 11px; color: var(--mu); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ln-meta { font-size: 10.5px; color: var(--mu-2); }
  .ins-none { margin: 0; font-size: 11.5px; color: var(--mu-2); }
  .ins-sub {
    margin: 12px 0 6px;
    font-size: 10.5px;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--mu-2);
    font-weight: 700;
  }
  .ln-btn {
    display: block;
    width: 100%;
    text-align: start;
    background: var(--surf-2);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 7px 9px;
    cursor: pointer;
    transition: border-color .15s, background .15s;
  }
  .ln-btn:hover { border-color: var(--n-louaj); background: rgba(0, 229, 192, .08); }
  .ln-btn:focus-visible { outline: 2px solid var(--n-louaj); outline-offset: 2px; }

  .inspector::-webkit-scrollbar { width: 8px; }
  .inspector::-webkit-scrollbar-track { background: transparent; }
  .inspector::-webkit-scrollbar-thumb {
    background: rgba(200, 180, 255, 0.16); border-radius: 4px;
    border: 2px solid transparent; background-clip: content-box;
  }
  .inspector::-webkit-scrollbar-thumb:hover {
    background: rgba(200, 180, 255, 0.32); background-clip: content-box;
  }

  @media (max-width: 900px) {
    .inspector {
      top: auto; bottom: 12px; inset-inline: 12px;
      width: auto; max-height: 52%;
    }
  }
</style>
