<script lang="ts">
  import { goto } from '$app/navigation';
  import { login, register } from '$lib/stores/auth.js';

  let mode: 'login' | 'register' = 'login';
  let email = '';
  let password = '';
  let displayName = '';
  let error = '';
  let loading = false;

  async function submit() {
    error = '';
    loading = true;
    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await register(email, password, displayName || undefined);
      }
      goto('/');
    } catch (e: any) {
      error = e.message || 'Something went wrong';
    } finally {
      loading = false;
    }
  }
</script>

<div class="min-h-screen flex items-center justify-center bg-slate-950 px-4">
  <div class="w-full max-w-md">
    <div class="text-center mb-8">
      <h1 class="text-3xl font-bold text-cyan-400">bledi.tn</h1>
      <p class="text-slate-400 mt-2">Tunisia transit routing app</p>
    </div>

    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-6">
      <div class="flex mb-6 bg-slate-800 rounded-lg p-1">
        <button
          class="flex-1 py-2 rounded-md text-sm font-medium transition {mode === 'login' ? 'bg-cyan-500 text-slate-950' : 'text-slate-400 hover:text-slate-200'}"
          on:click={() => (mode = 'login')}
        >Login</button>
        <button
          class="flex-1 py-2 rounded-md text-sm font-medium transition {mode === 'register' ? 'bg-cyan-500 text-slate-950' : 'text-slate-400 hover:text-slate-200'}"
          on:click={() => (mode = 'register')}
        >Register</button>
      </div>

      <form on:submit|preventDefault={submit} class="space-y-4">
        {#if mode === 'register'}
          <div>
            <label class="block text-sm text-slate-400 mb-1">Display name</label>
            <input
              type="text"
              bind:value={displayName}
              class="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-cyan-500"
              placeholder="Achref"
            />
          </div>
        {/if}

        <div>
          <label class="block text-sm text-slate-400 mb-1">Email</label>
          <input
            type="email"
            bind:value={email}
            required
            class="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-cyan-500"
            placeholder="you@example.com"
          />
        </div>

        <div>
          <label class="block text-sm text-slate-400 mb-1">Password</label>
          <input
            type="password"
            bind:value={password}
            required
            minlength="6"
            class="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-cyan-500"
            placeholder="Min 6 characters"
          />
        </div>

        {#if error}
          <div class="text-red-400 text-sm bg-red-950/50 border border-red-800 rounded-lg px-3 py-2">{error}</div>
        {/if}

        <button
          type="submit"
          disabled={loading}
          class="w-full py-2.5 bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-500 text-slate-950 font-semibold rounded-lg transition"
        >
          {loading ? 'Loading...' : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
      </form>
    </div>
  </div>
</div>
