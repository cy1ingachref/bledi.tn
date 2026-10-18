<script>
  import '@fontsource-variable/readex-pro';
  import '../../app.css';

  let email = $state('');
  let password = $state('');
  let error = $state('');
  let loading = $state(false);

  function validate() {
    error = '';
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      error = 'Please enter a valid email address.';
      return false;
    }
    if (!password || password.length < 6) {
      error = 'Password must be at least 6 characters.';
      return false;
    }
    return true;
  }

  function signIn() {
    if (!validate()) return;
    loading = true;
    const name = email.split('@')[0];
    const token = btoa(`${email}:${Date.now()}`);
    localStorage.setItem('bledi_auth', JSON.stringify({ email, name, token }));
    loading = false;
    window.location.href = '/';
  }

  function signUp() {
    if (!validate()) return;
    loading = true;
    const name = email.split('@')[0];
    const token = btoa(`${email}:${Date.now()}`);
    localStorage.setItem('bledi_auth', JSON.stringify({ email, name, token }));
    loading = false;
    window.location.href = '/';
  }

  function handleSubmit(e) {
    e.preventDefault();
    signIn();
  }
</script>

<svelte:head>
  <title>Sign in — bledi.tn</title>
</svelte:head>

<div class="note">Design preview · bledi.tn</div>

<div class="login-wrap">
  <div class="login-card">
    <header class="login-header">
      <h1>bledi<span>.tn</span></h1>
      <div class="langs" role="group" aria-label="Language">
        <button aria-pressed="true" onclick={() => {}}>FR</button>
        <button onclick={() => {}}>ع</button>
        <button onclick={() => {}}>EN</button>
      </div>
    </header>

    <p class="sub">Sign in to your account</p>

    <form onsubmit={handleSubmit} novalidate>
      <div class="field">
        <label for="email">Email</label>
        <input
          id="email"
          type="email"
          bind:value={email}
          placeholder="you@example.com"
          autocomplete="email"
          required
        />
      </div>

      <div class="field">
        <label for="password">Password</label>
        <input
          id="password"
          type="password"
          bind:value={password}
          placeholder="••••••••"
          autocomplete="current-password"
          required
        />
      </div>

      {#if error}
        <p class="error">{error}</p>
      {/if}

      <button type="submit" class="btn-signin" disabled={loading}>
        {loading ? 'Signing in…' : 'Sign in'}
      </button>
    </form>

    <div class="alt">
      <span>Don't have an account?</span>
      <button class="btn-link" onclick={signUp}>Sign up</button>
    </div>
  </div>
</div>

<style>
  .login-wrap {
    min-height: 100dvh;
    display: grid;
    place-items: center;
    background: var(--ink);
    padding: 16px;
    position: relative;
  }

  .note {
    position: absolute;
    top: 12px;
    right: 12px;
    z-index: 10;
    background: #0F2230;
    color: #fff;
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 0.8rem;
    opacity: 0.9;
    font-family: 'Readex Pro Variable', system-ui, sans-serif;
  }

  .login-card {
    width: 100%;
    max-width: 420px;
    background: var(--paper);
    border-radius: 24px;
    padding: 44px 36px 36px;
    box-shadow: 0 24px 70px rgba(15, 34, 48, 0.45), 0 8px 24px rgba(15, 34, 48, 0.2);
    position: relative;
  }

  .login-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .login-header h1 {
    margin: 0;
    font-size: 1.8rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1;
  }
  .login-header h1 span { color: var(--sea); }

  .langs {
    display: flex;
    gap: 4px;
  }
  .langs button {
    min-width: 40px;
    height: 36px;
    border: 1.5px solid var(--rule);
    border-radius: 10px;
    background: #fff;
    color: var(--ink);
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }
  .langs button[aria-pressed='true'] {
    background: var(--ink);
    border-color: var(--ink);
    color: #fff;
  }
  .langs button:hover:not([aria-pressed='true']) {
    border-color: var(--sea);
  }

  .sub {
    margin: 0 0 28px;
    color: var(--muted);
    font-size: 1rem;
  }

  form { display: grid; gap: 18px; }

  .field { display: grid; gap: 6px; }
  .field label {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--ink);
    letter-spacing: -0.01em;
  }

  .field input {
    height: 48px;
    padding: 0 16px;
    border: 1.5px solid var(--rule);
    border-radius: 12px;
    font-size: 1rem;
    background: #fff;
    color: var(--ink);
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .field input::placeholder { color: var(--muted); opacity: 0.7; }
  .field input:focus {
    outline: none;
    border-color: var(--sea);
    box-shadow: 0 0 0 3px rgba(31, 111, 139, 0.12), 0 0 0 5px rgba(244, 180, 0, 0.06);
  }

  .error {
    margin: 0;
    color: var(--red);
    font-size: 0.85rem;
    text-align: center;
    font-weight: 500;
  }

  .btn-signin {
    height: 50px;
    border: none;
    border-radius: 12px;
    background: var(--ink);
    color: #fff;
    font-size: 1rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    cursor: pointer;
    transition: background 0.2s, transform 0.1s;
    box-shadow: 0 4px 14px rgba(15, 34, 48, 0.25);
  }
  .btn-signin:hover:not(:disabled) {
    background: #16304A;
  }
  .btn-signin:active:not(:disabled) {
    transform: translateY(1px);
  }
  .btn-signin:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .alt {
    margin-top: 24px;
    text-align: center;
    font-size: 0.875rem;
    color: var(--muted);
    display: flex;
    justify-content: center;
    gap: 6px;
    align-items: center;
  }

  .btn-link {
    background: none;
    border: none;
    color: var(--sea);
    font-weight: 600;
    cursor: pointer;
    font-size: inherit;
    padding: 0;
    transition: color 0.15s;
  }
  .btn-link:hover { color: var(--ink); text-decoration: underline; }

  @media (max-width: 480px) {
    .login-card { padding: 36px 24px 28px; border-radius: 20px; }
    .login-header h1 { font-size: 1.5rem; }
  }
</style>
