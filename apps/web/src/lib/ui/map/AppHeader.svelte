<script lang="ts">
  import Icon from "$lib/ui/Icon.svelte";
  import { LANGS, type Lang, type Translate } from "$lib/application/i18n";
  import { cycleTheme, themePref } from "$lib/ui/theme";

  let { lang = $bindable(), t }: { lang: Lang; t: Translate } = $props();

  const themeIcon = $derived($themePref === "auto" ? "globe" : $themePref === "light" ? "sun" : "moon");
  const themeLabel = $derived(
    $themePref === "auto" ? t("theme.auto") : $themePref === "light" ? t("theme.light") : t("theme.dark")
  );
</script>

<header class="hdr">
  <div class="brand">
    <span class="brand-mark" aria-hidden="true"><Icon name="route" size={20} /></span>
    <span class="brand-text">
      <strong>Bledi<span class="dot">.tn</span></strong>
      <small>{t("app.tagline")}</small>
    </span>
  </div>
  <div class="hdr-right">
    <button class="theme-btn" onclick={cycleTheme} aria-label={themeLabel} title={themeLabel}>
      <Icon name={themeIcon} size={16} />
    </button>
    <div class="langs" role="group" aria-label="Language">
      {#each LANGS as l (l.id)}
        <button
          class="lang"
          class:on={lang === l.id}
          onclick={() => (lang = l.id)}
          aria-pressed={lang === l.id}
          title={l.label}
        >{l.short}</button>
      {/each}
    </div>
  </div>
</header>

<style>
  .hdr {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    padding: 12px 18px;
    background: var(--surf);
    border-bottom: 1px solid var(--line);
    backdrop-filter: blur(18px) saturate(1.3);
    flex-shrink: 0;
    z-index: 600;
    transition: background 0.35s ease, border-color 0.35s ease;
  }
  .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .brand-mark {
    display: grid; place-items: center;
    width: 42px; height: 42px; flex-shrink: 0;
    border-radius: 14px;
    background: linear-gradient(135deg, var(--a1), var(--a2));
    color: var(--on-accent);
    box-shadow: 0 0 22px rgba(123, 92, 255, 0.5), 0 8px 24px rgba(0, 0, 0, 0.5);
    animation: float 4s ease-in-out infinite;
  }
  @keyframes float { 50% { transform: translateY(-3px) rotate(-4deg); } }
  .brand-text { display: flex; flex-direction: column; min-width: 0; }
  .brand-text strong { font-family: "Sora", system-ui, sans-serif; font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }
  .brand-text .dot {
    background: linear-gradient(90deg, var(--a1), var(--a2));
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .brand-text small { color: var(--mu); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .hdr-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

  .theme-btn {
    display: grid; place-items: center;
    width: 34px; height: 34px;
    border-radius: 99px;
    border: 1px solid var(--line);
    background: var(--surf-2);
    color: var(--tx);
    cursor: pointer;
    transition: transform 0.25s ease, border-color 0.25s ease, color 0.25s ease;
  }
  .theme-btn:hover { border-color: var(--a1); color: var(--a1); transform: rotate(-12deg) scale(1.06); }

  .langs { display: flex; gap: 2px; padding: 3px; border: 1px solid var(--line); border-radius: 99px; background: var(--surf-2); flex-shrink: 0; }
  .lang {
    min-width: 34px; min-height: 28px;
    border: 0; border-radius: 99px;
    background: transparent; color: var(--mu);
    font: inherit; font-size: 11px; font-weight: 700;
    cursor: pointer;
    transition: background 0.25s ease, color 0.25s ease;
  }
  .lang:hover { color: var(--tx); background: var(--surf-2); }
  .lang.on { background: linear-gradient(135deg, var(--a1), var(--a2)); color: var(--on-accent); }

  @media (max-width: 420px) {
    .hdr { padding: 10px 13px; }
    .brand-text small { display: none; }
  }
</style>
