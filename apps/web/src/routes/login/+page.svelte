<script>
  import '@fontsource/courier-prime/400.css';
  import '@fontsource/courier-prime/700.css';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import LangSwitch from '$lib/LangSwitch.svelte';
  import { ui } from '$lib/ui.svelte.js';
  import { loginUser } from '$lib/api.js';

  const copy = {
    fr: { card: 'Carte d’usager', title: 'Connexion', sub: 'Retrouvez vos trajets enregistrés.', email: 'Email', pass: 'Mot de passe', submit: 'Se connecter', forgot: 'Mot de passe oublié ?', create: 'Créer un compte', guest: 'Continuer sans compte', error: 'Email ou mot de passe incorrect' },
    ar: { card: 'بطاقة المستخدم', title: 'تسجيل الدخول', sub: 'استرجع مساراتك المحفوظة.', email: 'البريد', pass: 'كلمة السر', submit: 'تسجيل الدخول', forgot: 'نسيت كلمة السر؟', create: 'إنشاء حساب', guest: 'المتابعة بدون حساب', error: 'البريد أو كلمة السر غير صحيح' },
    en: { card: 'Rider card', title: 'Log in', sub: 'Pick up your saved routes.', email: 'Email', pass: 'Password', submit: 'Log in', forgot: 'Forgot password?', create: 'Create account', guest: 'Continue without an account', error: 'Invalid email or password' }
  };
  const t = $derived(copy[ui.lang]);

  let today = $state('');
  let punched = $state(false);
  let error = $state('');
  let loading = $state(false);

  onMount(() => {
    const d = new Date(), p = (n) => String(n).padStart(2, '0');
    today = `${p(d.getDate())}.${p(d.getMonth() + 1)}.${String(d.getFullYear()).slice(2)}`;
  });

  async function submit(e) {
    e.preventDefault();
    const email = e.currentTarget.email?.value?.trim();
    const password = e.currentTarget.password?.value;
    if (!email || !password) {
      error = t.error;
      return;
    }
    punched = true;
    loading = true;
    error = '';
    try {
      const result = await loginUser({ email, password });
      const auth = {
        email,
        token: result?.token || result?.access_token || 'local-demo',
      };
      localStorage.setItem('bledi_auth', JSON.stringify(auth));
      await goto(resolve('/'));
    } catch (err) {
      error = err?.message || t.error;
      punched = false;
    } finally {
      loading = false;
    }
  }
</script>

<main class="scene">
  <div class="lang"><LangSwitch /></div>

  <div class="wrap">
    <div class="ticket">
      <div class="band"><strong>bledi.tn</strong><span>{t.card}</span></div>

      <form onsubmit={submit}>
        <svg class="stamp" viewBox="0 0 120 120" aria-hidden="true">
          <defs><path id="ring" d="M60,60 m-44,0 a44,44 0 1,1 88,0 a44,44 0 1,1 -88,0" /></defs>
          <circle cx="60" cy="60" r="57" /><circle cx="60" cy="60" r="30" />
          <text class="ring"><textPath href="#ring">BLEDI.TN • TUNIS • BLEDI.TN • TUNIS •</textPath></text>
          <text class="date" x="60" y="64" text-anchor="middle">{today}</text>
        </svg>

        <div class="head">
          <h1>{t.title}</h1>
          <p>{t.sub}</p>
        </div>

        <label class="field"><span>{t.email}</span><input type="email" name="email" autocomplete="username" required /></label>
        <label class="field"><span>{t.pass}</span><input type="password" name="password" autocomplete="current-password" required /></label>

        <div class="action">
          <button class="go" disabled={punched && loading}>{loading ? '...' : t.submit}</button>
          {#if punched && loading}<i class="punch"></i>{/if}
        </div>
        {#if error}<p class="error">{error}</p>{/if}
        <div class="links">
          <button type="button" class="link-btn">{t.forgot}</button>
          <button type="button" class="link-btn">{t.create}</button>
        </div>
      </form>

      <div class="stub">
        <div><small>N° 000417</small><button type="button" class="link-btn" onclick={() => { localStorage.setItem('bledi_auth', JSON.stringify({email:'guest',token:'guest'})); goto(resolve('/')); }}>{t.guest}</button></div>
        <i class="bars"></i>
      </div>
    </div>
  </div>

  <div class="track" aria-hidden="true"></div>
</main>

<style>
  .scene {
    --cut: 96px; position: relative; min-height: 100dvh; display: grid; grid-template-columns: minmax(0, 1fr); place-items: center; overflow: hidden;
    padding: 72px 16px 96px; background: radial-gradient(ellipse at 50% 35%, #214559, #0f2230 72%);
  }
  .scene::before {
    content: ''; position: absolute; inset: 0; opacity: 0.08; pointer-events: none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='2'/><feColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .6 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
  }
  .lang { position: absolute; top: 16px; inset-inline-end: 16px; z-index: 2; }
  .track {
    position: absolute; inset-inline: 0; bottom: 0; height: 56px; opacity: 0.5;
    background:
      linear-gradient(#8aa0ab, #8aa0ab) 0 10px / 100% 3px no-repeat,
      linear-gradient(#8aa0ab, #8aa0ab) 0 38px / 100% 3px no-repeat,
      repeating-linear-gradient(90deg, #2a4252 0 12px, transparent 12px 40px);
  }

  .wrap { position: relative; z-index: 1; width: min(100%, 420px); filter: drop-shadow(0 18px 24px #0009); }
  .ticket {
    position: relative; overflow: hidden; border-radius: 6px; color: #1b3a4b;
    font-family: 'Courier Prime', 'Readex Pro Variable', monospace;
    background: radial-gradient(#0000000c 1px, transparent 1.5px) 0 0 / 5px 5px, #c9dde6;
    -webkit-mask: radial-gradient(circle 11px at 0 calc(100% - var(--cut)), #0000 98%, #000) left / 51% 100% no-repeat,
                  radial-gradient(circle 11px at 100% calc(100% - var(--cut)), #0000 98%, #000) right / 51% 100% no-repeat;
    mask: radial-gradient(circle 11px at 0 calc(100% - var(--cut)), #0000 98%, #000) left / 51% 100% no-repeat,
          radial-gradient(circle 11px at 100% calc(100% - var(--cut)), #0000 98%, #000) right / 51% 100% no-repeat;
  }
  .band { display: flex; justify-content: space-between; align-items: baseline; padding: 11px 20px; background: var(--red); color: #fff; border-bottom: 4px double #ffffff99; }
  .band strong { font-size: 1.15rem; }
  form { position: relative; padding: 22px 22px 20px; }

  .stamp { position: absolute; top: 8px; inset-inline-end: 12px; width: 92px; rotate: -14deg; fill: none; stroke: #a3262a; stroke-width: 2; opacity: 0.72; mix-blend-mode: multiply; }
  .stamp text { fill: #a3262a; stroke: none; font: 700 10px 'Courier Prime', monospace; letter-spacing: 0.5px; }
  .stamp .date { font-size: 11px; letter-spacing: 0; }

  .head { padding-inline-end: 96px; }
  h1 { margin: 0; font: 700 1.7rem/1.2 'Readex Pro Variable', sans-serif; letter-spacing: -0.01em; }
  .head p { margin: 4px 0 0; font-size: 0.9rem; }

  .field { display: flex; align-items: baseline; gap: 10px; margin-top: 20px; }
  .field span { flex: 0 0 12ch; font-weight: 700; }
  .field input { flex: 1; min-width: 0; padding: 5px 4px; border: 0; border-bottom: 2px dotted #3b6277; border-radius: 0; background: #ffffff40; font: inherit; }

  .action { position: relative; margin-top: 24px; }
  .go { width: 100%; padding: 13px; border: 0; border-radius: 3px; background: var(--ink); color: #c9dde6; font: 700 1rem 'Courier Prime', 'Readex Pro Variable', monospace; }
  .go:hover:not(:disabled) { background: #1c3a4e; }
  .punch {
    position: absolute; left: 50%; top: 50%; width: 44px; height: 44px; margin: -22px 0 0 -22px; border-radius: 50%;
    background: #0f2230; box-shadow: inset 0 3px 6px #000b; animation: punch 0.35s cubic-bezier(0.3, 1.6, 0.5, 1) both;
  }
  @keyframes punch { from { scale: 0; } to { scale: 1; } }

  .links { display: flex; justify-content: space-between; gap: 12px; margin-top: 14px; font-size: 0.85rem; }
  .link-btn {
    background: transparent; border: 0; padding: 0; color: inherit;
    text-decoration: underline; cursor: pointer; font: inherit; font-size: 0.85rem;
  }
  .link-btn:hover { color: var(--ink); }
  .error { background: #fde8e8; color: #9b1c1c; padding: 8px 12px; border-radius: 4px; font-size: 0.85rem; margin-top: 10px; }
  a { color: inherit; }

  .stub { box-sizing: border-box; height: var(--cut); padding: 0 22px; display: flex; justify-content: space-between; align-items: center; border-top: 2px dashed #6f8c9b; }
  .stub div { display: grid; gap: 4px; font-size: 0.85rem; }
  .stub small { color: var(--red); font-size: 0.85rem; font-weight: 700; }
  .bars { width: 90px; height: 36px; background: repeating-linear-gradient(90deg, #1b3a4b 0 2px, transparent 2px 4px, #1b3a4b 4px 5px, transparent 5px 8px, #1b3a4b 8px 11px, transparent 11px 13px); }
</style>
