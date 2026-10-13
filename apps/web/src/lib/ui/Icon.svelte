<script lang="ts">
  // Vector icon set (stroke-based, single family, consistent 1.75 stroke).
  // No emoji used as structural icons anywhere in the app: they are
  // font-dependent, unthemeable, and render as tofu boxes on a bare install.
  let { name, size = 20, stroke = 1.75, cls = "" }: {
    name: string;
    size?: number;
    stroke?: number;
    cls?: string;
  } = $props();

  const PATHS: Record<string, string> = {
    bus: '<rect x="4" y="3" width="16" height="14" rx="2.5"/><path d="M4 10.5h16"/><path d="M7.5 17.5V19M16.5 17.5V19"/><circle cx="8.5" cy="14" r=".9"/><circle cx="15.5" cy="14" r=".9"/>',
    metro: '<circle cx="12" cy="12" r="9"/><path d="M8.2 16V8.6l3.8 4 3.8-4V16"/>',
    tram: '<rect x="5.5" y="4.5" width="13" height="11.5" rx="2.5"/><path d="M5.5 9.5h13"/><path d="M12 4.5V2.5M9.5 16l-2 4M14.5 16l2 4M7.5 20h9"/><circle cx="9" cy="13" r=".9"/><circle cx="15" cy="13" r=".9"/>',
    train: '<rect x="5" y="3.5" width="14" height="12.5" rx="2.5"/><path d="M5 10h14"/><path d="M9 16l-2.2 4.2M15 16l2.2 4.2M7.2 20.2h9.6"/><circle cx="9" cy="13" r=".9"/><circle cx="15" cy="13" r=".9"/>',
    taxi: '<path d="M5 17.5V11l1.8-4.3A1.4 1.4 0 0 1 8.1 5.8h7.8a1.4 1.4 0 0 1 1.3.9L19 11v6.5"/><path d="M5 17.5h14"/><path d="M7.4 5.8l-.9-2.3M16.6 5.8l.9-2.3"/><path d="M9.2 9.5h5.6"/><circle cx="8" cy="17.6" r="1.7"/><circle cx="16" cy="17.6" r="1.7"/>',
    walk: '<circle cx="13.2" cy="4.3" r="1.7"/><path d="M10.4 21.2l1.7-6.1M12.1 15.1l-2.2-3.2 3.2-2.1 2.1 3.1M9.9 11.9l-2.1 3.2M14.2 15.1l2.2 5.6"/>',
    pin: '<path d="M12 21.2s-7-5.6-7-11.1a7 7 0 1 1 14 0c0 5.5-7 11.1-7 11.1z"/><circle cx="12" cy="10" r="2.6"/>',
    locate: '<circle cx="12" cy="12" r="6.5"/><path d="M12 2.2v3.1M12 18.7v3.1M2.2 12h3.1M18.7 12h3.1"/><circle cx="12" cy="12" r="2.1"/>',
    crosshair: '<circle cx="12" cy="12" r="8.4"/><path d="M12 1.6v4.2M12 18.2v4.2M1.6 12h4.2M18.2 12h4.2"/><circle cx="12" cy="12" r="1.6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6.8v5.4l3.2 1.9"/>',
    coin: '<rect x="2.4" y="6.2" width="19.2" height="11.6" rx="2.2"/><circle cx="12" cy="12" r="2.5"/><path d="M6.2 12h.02M17.8 12h.02"/>',
    transfer: '<path d="M6.5 3.6L3.4 6.7l3.1 3.1"/><path d="M3.4 6.7h11.2a4.1 4.1 0 0 1 0 8.2H9.2"/><path d="M11.8 18.3l3.1-3.1"/>',
    close: '<path d="M6.4 6.4l11.2 11.2M17.6 6.4L6.4 17.6"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3.1 12h17.8M12 3a13.6 13.6 0 0 1 0 18A13.6 13.6 0 0 1 12 3z"/>',
    search: '<circle cx="11" cy="11" r="6.8"/><path d="M20.2 20.2l-4.4-4.4"/>',
    alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.6v5.2M12 16.4h.02"/>',
    network: '<circle cx="5.5" cy="5.5" r="2.4"/><circle cx="18.5" cy="8" r="2.4"/><circle cx="8" cy="18" r="2.4"/><path d="M7.7 6.4l8.6 1.1M6.4 7.7l1.1 8.1M16.7 9.7l-6.9 6.7"/>',
    eye: '<path d="M2.2 12S5.8 5.6 12 5.6 21.8 12 21.8 12 18.2 18.4 12 18.4 2.2 12 2.2 12z"/><circle cx="12" cy="12" r="2.9"/>',
    eyeOff: '<path d="M10.6 6a9.6 9.6 0 0 1 1.4-.1c6.2 0 9.8 6.1 9.8 6.1a17 17 0 0 1-2.9 3.6"/><path d="M6.3 7.6A17 17 0 0 0 2.2 12s3.6 6.1 9.8 6.1a9.4 9.4 0 0 0 4-.9"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="M3.2 3.2l17.6 17.6"/>',
    arrowRight: '<path d="M4.5 12h15M13 6l6 6-6 6"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11.2v5.2M12 7.9h.02"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.2"/><circle cx="12" cy="12" r="1"/>',
    // The design's brand glyph: an S-curve route between two stops.
    route: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.5 6H14a3 3 0 010 6h-4a3 3 0 000 6h5.5"/>'
  };

  const d = $derived(PATHS[name] ?? PATHS.pin);
</script>

<svg
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill="none"
  stroke="currentColor"
  stroke-width={stroke}
  stroke-linecap="round"
  stroke-linejoin="round"
  class={cls}
  aria-hidden="true"
>
  {@html d}
</svg>
