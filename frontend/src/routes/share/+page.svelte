<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { isAuthenticated } from '$lib/stores/auth.ts';
  import { userLocation } from '$lib/stores/location.ts';
  import type { LocationShare } from '$lib/types.js';

  let shares = $state<LocationShare[]>([]);
  let nearbyShares = $state<LocationShare[]>([]);
  let loading = $state(true);
  let sharing = $state(false);
  let note = $state('');
  let shareError = $state('');

  $effect(() => {
    if (!$isAuthenticated) goto('/auth');
  });

  onMount(async () => {
    await loadShares();
    await loadNearby();
  });

  function authHeaders(): Record<string, string> {
    const t = localStorage.getItem('bledi_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
  }

  async function loadShares() {
    loading = true;
    try {
      const res = await fetch('/api/v1/location-shares', { headers: authHeaders() });
      if (res.ok) shares = await res.json();
    } catch (e) {
      // ignore
    } finally {
      loading = false;
    }
  }

  async function loadNearby() {
    try {
      const loc = await userLocation.locate();
      const res = await fetch(
        `/api/v1/location-shares/nearby?lat=${loc.lat}&lon=${loc.lon}&radius_m=5000`,
        { headers: authHeaders() }
      );
      if (res.ok) nearbyShares = await res.json();
    } catch (e) {
      // ignore
    }
  }

  async function startSharing() {
    shareError = '';
    try {
      const loc = await userLocation.locate();
      const res = await fetch('/api/v1/location-shares', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          lat: loc.lat,
          lon: loc.lon,
          accuracy_m: null,
          note: note || null,
          is_active: true,
          expires_at: null
        })
      });
      if (!res.ok) throw new Error((await res.json()).error || 'Failed');
      sharing = true;
      note = '';
      await loadShares();
    } catch (e: any) {
      shareError = e.message;
    }
  }

  async function stopSharing() {
    for (const s of shares.filter((s) => s.is_active)) {
      await fetch(`/api/v1/location-shares/${s.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ lat: s.lat, lon: s.lon, accuracy_m: s.accuracy_m, note: s.note, is_active: false, expires_at: s.expires_at })
      });
    }
    sharing = false;
    await loadShares();
  }

  function formatTime(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
</script>

<div class="min-h-screen bg-slate-950 pb-20">
  <header class="sticky top-0 z-10 bg-slate-950/90 backdrop-blur border-b border-slate-800 px-4 py-3">
    <div class="flex items-center justify-between">
      <a href="/" class="text-cyan-400 font-bold text-lg">bledi.tn</a>
      <span class="text-slate-400 text-sm">Share Location</span>
    </div>
  </header>

  <main class="px-4 py-4 space-y-4">
    {#if nearbyShares.length > 0}
      <div class="bg-cyan-950/50 border border-cyan-800 rounded-xl p-3">
        <div class="text-cyan-400 text-sm font-medium mb-2">
          {nearbyShares.length} friend{nearbyShares.length > 1 ? 's' : ''} nearby
        </div>
        <div class="space-y-2">
          {#each nearbyShares as s}
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 rounded-full bg-cyan-500 flex items-center justify-center text-slate-950 text-sm font-bold">
                {s.user_id.charAt(0).toUpperCase()}
              </div>
              <div>
                <div class="text-slate-200 text-sm">Friend #{s.user_id.slice(0, 8)}</div>
                <div class="text-slate-500 text-xs">{formatTime(s.updated_at)}</div>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <div class="bg-slate-900 rounded-2xl border border-slate-800 p-4 space-y-3">
      <h3 class="text-slate-100 font-medium">Share your location</h3>
      <p class="text-slate-400 text-sm">Friends nearby can see your live location.</p>

      {#if !sharing}
        <input
          type="text"
          bind:value={note}
          placeholder="Note (optional)"
          class="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm"
        />
        {#if shareError}
          <div class="text-red-400 text-sm">{shareError}</div>
        {/if}
        <button
          onclick={startSharing}
          class="w-full py-2.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold rounded-xl transition"
        >
          Start Sharing
        </button>
      {:else}
        <div class="text-center py-4">
          <div class="w-12 h-12 rounded-full bg-green-500/20 border-2 border-green-500 mx-auto flex items-center justify-center mb-3">
            <div class="w-3 h-3 rounded-full bg-green-500 animate-pulse"></div>
          </div>
          <div class="text-green-400 font-medium">Sharing active</div>
          <div class="text-slate-500 text-sm mt-1">Friends can see your location</div>
          <button
            onclick={stopSharing}
            class="mt-4 px-6 py-2 bg-red-500/20 text-red-400 border border-red-500/50 rounded-xl text-sm font-medium"
          >Stop Sharing</button>
        </div>
      {/if}
    </div>

    {#if shares.length > 0}
      <div>
        <h4 class="text-slate-400 text-sm font-medium mb-2">Your shares</h4>
        <div class="space-y-2">
          {#each shares as s}
            <div class="bg-slate-900 rounded-xl border border-slate-800 px-4 py-3 flex items-center justify-between">
              <div>
                <div class="text-slate-200 text-sm">{s.note || 'No note'}</div>
                <div class="text-slate-500 text-xs">{formatTime(s.created_at)} · {s.is_active ? 'Active' : 'Inactive'}</div>
              </div>
              <span class="text-xs px-2 py-1 rounded-full {s.is_active ? 'bg-green-500/20 text-green-400' : 'bg-slate-800 text-slate-500'}">
                {s.is_active ? 'Live' : 'Off'}
              </span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </main>
</div>
