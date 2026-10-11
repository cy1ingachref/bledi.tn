<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { isAuthenticated } from '$lib/stores/auth.ts';
  import type { Favorite } from '$lib/types.js';

  let favorites = $state<Favorite[]>([]);
  let loading = $state(true);
  let error = $state('');
  $effect(() => {
    if (!$isAuthenticated) goto('/auth');
  });

  onMount(loadFavorites);

  async function loadFavorites() {
    loading = true;
    try {
      const res = await fetch('/api/v1/favorites', {
        headers: { Authorization: 'Bearer ' + localStorage.getItem('bledi_token') }
      });
      if (res.ok) favorites = await res.json();
    } catch (e) {
      // ignore
    } finally {
      loading = false;
    }
  }

  async function removeFavorite(id: string) {
    await fetch(`/api/v1/favorites/${id}`, {
      method: 'DELETE',
      headers: { Authorization: 'Bearer ' + localStorage.getItem('bledi_token') }
    });
    favorites = favorites.filter((f) => f.id !== id);
  }

  function kindIcon(kind: string): string {
    switch (kind) {
      case 'station': return '🚏';
      case 'line': return '🚌';
      case 'place': return '📍';
      default: return '⭐';
    }
  }
</script>

<div class="min-h-screen bg-slate-950 pb-20">
  <header class="sticky top-0 z-10 bg-slate-950/90 backdrop-blur border-b border-slate-800 px-4 py-3">
    <div class="flex items-center justify-between">
      <a href="/" class="text-cyan-400 font-bold text-lg">bledi.tn</a>
      <span class="text-slate-400 text-sm">Favorites</span>
    </div>
  </header>

  <main class="px-4 py-4">
    {#if loading}
      <div class="text-center text-slate-500 py-8">Loading...</div>
    {:else if favorites.length === 0}
      <div class="text-center text-slate-500 py-8">
        <p class="text-4xl mb-3">⭐</p>
        <p>No favorites yet.</p>
        <p class="text-sm mt-1">Save stations, lines, and places for quick access.</p>
      </div>
    {:else}
      <div class="space-y-2">
        {#each favorites as f}
          <div class="bg-slate-900 rounded-xl border border-slate-800 px-4 py-3 flex items-center justify-between">
            <div class="flex items-center gap-3">
              <span class="text-xl">{kindIcon(f.kind)}</span>
              <div>
                <div class="text-slate-100 text-sm font-medium">{f.label || f.ref_id}</div>
                <div class="text-slate-500 text-xs">{f.kind}</div>
              </div>
            </div>
            <button
              onclick={() => removeFavorite(f.id)}
              class="text-slate-600 hover:text-red-400 text-sm"
            >Remove</button>
          </div>
        {/each}
      </div>
    {/if}
  </main>
</div>
