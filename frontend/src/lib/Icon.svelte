<script lang="ts">
  // Vector icon set (stroke-based, single family, consistent 1.75 stroke).
  // No emoji used as structural icons.
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
    rfr: '<rect x="6" y="4" width="12" height="12" rx="2.5"/><path d="M6 10h12"/><path d="M10 16l-1.6 4M14 16l1.6 4"/><path d="M8.6 20h6.8"/>',
    louaj: '<path d="M3 16.5V9a1 1 0 0 1 1-1h8.6l4.2 3.2H19a1.5 1.5 0 0 1 1.5 1.5v3.8"/><path d="M3 16.5h18"/><path d="M3 12.5h10"/><circle cx="7.5" cy="17.8" r="1.6"/><circle cx="16.5" cy="17.8" r="1.6"/>',
    taxi: '<path d="M5 17.5V11l1.8-4.3A1.4 1.4 0 0 1 8.1 5.8h7.8a1.4 1.4 0 0 1 1.3.9L19 11v6.5"/><path d="M5 17.5h14"/><path d="M7.4 5.8l-.9-2.3M16.6 5.8l.9-2.3"/><path d="M9.2 9.5h5.6"/><circle cx="8" cy="17.6" r="1.7"/><circle cx="16" cy="17.6" r="1.7"/>',
    walk: '<circle cx="13.2" cy="4.3" r="1.7"/><path d="M10.4 21.2l1.7-6.1M12.1 15.1l-2.2-3.2 3.2-2.1 2.1 3.1M9.9 11.9l-2.1 3.2M14.2 15.1l2.2 5.6"/>',
    pin: '<path d="M12 21.2s-7-5.6-7-11.1a7 7 0 1 1 14 0c0 5.5-7 11.1-7 11.1z"/><circle cx="12" cy="10" r="2.6"/>',
    check: '<path d="M5 12.6l4.6 4.6L19 7.4"/>',
    locate: '<circle cx="12" cy="12" r="6.5"/><path d="M12 2.2v3.1M12 18.7v3.1M2.2 12h3.1M18.7 12h3.1"/><circle cx="12" cy="12" r="2.1"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6.8v5.4l3.2 1.9"/>',
    coin: '<rect x="2.4" y="6.2" width="19.2" height="11.6" rx="2.2"/><circle cx="12" cy="12" r="2.5"/><path d="M6.2 12h.02M17.8 12h.02"/>',
    transfer: '<path d="M6.5 3.6L3.4 6.7l3.1 3.1"/><path d="M3.4 6.7h11.2a4.1 4.1 0 0 1 0 8.2H9.2"/><path d="M11.8 18.3l3.1-3.1"/>',
    close: '<path d="M6.4 6.4l11.2 11.2M17.6 6.4L6.4 17.6"/>',
    chevron: '<path d="M6.5 9.5l5.5 5.5 5.5-5.5"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3.1 12h17.8M12 3a13.6 13.6 0 0 1 0 18A13.6 13.6 0 0 1 12 3z"/>',
    search: '<circle cx="11" cy="11" r="6.8"/><path d="M20.2 20.2l-4.4-4.4"/>',
    alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7.6v5.2M12 16.4h.02"/>',
    layers: '<path d="M12 3.2l9 4.6-9 4.6-9-4.6 9-4.6z"/><path d="M3 12.4l9 4.6 9-4.6"/><path d="M3 16.6l9 4.6 9-4.6"/>',
    route: '<circle cx="6.2" cy="5.6" r="2.4"/><circle cx="17.8" cy="18.4" r="2.4"/><path d="M6.2 8v5.2a3.2 3.2 0 0 0 3.2 3.2h5.6"/>'
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
