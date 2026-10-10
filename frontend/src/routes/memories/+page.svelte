<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { isAuthenticated } from '$lib/stores/auth.js';
  import { userLocation } from '$lib/stores/location.js';
  import type { Memory, CreateMemoryRequest } from '$lib/types.js';

  let memories: Memory[] = [];
  let loading = true;
  let error = '';
  let captureMode = false;
  let captureLat = 0;
  let captureLon = 0;
  let mediaFile: File | null = null;
  let mediaPreview = '';
  let title = '';
  let description = '';
  let visibility: 'public' | 'friends' | 'private' = 'public';
  let unlockRadius = 200;
  let creating = false;
  let nearbyMemories: Memory[] = [];
  let showUnlocked = false;

  $: if (!$isAuthenticated) goto('/auth');

  onMount(async () => {
    await loadMemories();
    await loadNearby();
  });

  async function loadMemories() {
    loading = true;
    try {
      const res = await fetch('/api/v1/memories', {
        headers: authHeaders()
      });
      if (res.ok) memories = await res.json();
    } catch (e) {
      error = 'Failed to load memories';
    } finally {
      loading = false;
    }
  }

  async function loadNearby() {
    try {
      const loc = await userLocation.locate();
      const res = await fetch(
        `/api/v1/memories/nearby?lat=${loc.lat}&lon=${loc.lon}&radius_m=500`,
        { headers: authHeaders() }
      );
      if (res.ok) nearbyMemories = await res.json();
    } catch (e) {
      // Silently fail - location might be denied
    }
  }

  function authHeaders(): Record<string, string> {
    const t = localStorage.getItem('bledi_token');
    return t ? { Authorization: 'Bearer ' + t } : {};
  }

  async function startCapture() {
    try {
      const loc = await userLocation.locate();
      captureLat = loc.lat;
      captureLon = loc.lon;
      captureMode = true;
    } catch (e) {
      error = 'Location required to pin a memory';
    }
  }

  function onFileChange(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      mediaFile = input.files[0];
      const reader = new FileReader();
      reader.onload = () => (mediaPreview = reader.result as string);
      reader.readAsDataURL(mediaFile);
    }
  }

  async function createMemory() {
    if (!mediaFile) {
      error = 'Please select a photo or video';
      return;
    }
    creating = true;
    error = '';
    try {
      // In production, upload media to S3/R2 first, then create memory with URL
      // For now, use a placeholder URL
      const mediaUrl = mediaPreview || 'https://placeholder.com/memory.jpg';
      const req: CreateMemoryRequest = {
        lat: captureLat,
        lon: captureLon,
        title: title || undefined,
        description: description || undefined,
        media_url: mediaUrl,
        media_type: mediaFile.type.startsWith('video') ? 'video' : 'image',
        visibility,
        unlock_radius_m: unlockRadius
      };
      const res = await fetch('/api/v1/memories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(req)
      });
      if (!res.ok) throw new Error((await res.json()).error || 'Failed');
      await loadMemories();
      captureMode = false;
      mediaFile = null;
      mediaPreview = '';
      title = '';
      description = '';
    } catch (e: any) {
      error = e.message;
    } finally {
      creating = false;
    }
  }

  async function deleteMemory(id: string) {
    if (!confirm('Delete this memory?')) return;
    await fetch(`/api/v1/memories/${id}`, { method: 'DELETE', headers: authHeaders() });
    await loadMemories();
  }

  function isUnlocked(m: Memory): boolean {
    // In a real app, check distance from user location
    return m.visibility === 'public';
  }
</script>

<div class="min-h-screen bg-slate-950 pb-20">
  <header class="sticky top-0 z-10 bg-slate-950/90 backdrop-blur border-b border-slate-800 px-4 py-3">
    <div class="flex items-center justify-between">
      <a href="/" class="text-cyan-400 font-bold text-lg">bledi.tn</a>
      <span class="text-slate-400 text-sm">Memories</span>
    </div>
  </header>

  <main class="px-4 py-4 space-y-4">
    {#if nearbyMemories.length > 0}
      <div class="bg-cyan-950/50 border border-cyan-800 rounded-xl p-3">
        <div class="text-cyan-400 text-sm font-medium mb-2">
          {nearbyMemories.length} memor{y near you}
        </div>
        <div class="flex gap-2 overflow-x-auto">
          {#each nearbyMemories.slice(0, 5) as m}
            <div class="flex-shrink-0 w-20 text-center">
              <div class="w-16 h-16 rounded-full bg-slate-800 mx-auto overflow-hidden">
                <img src={m.media_url} alt="" class="w-full h-full object-cover" />
              </div>
              <div class="text-xs text-slate-400 mt-1 truncate">{m.title || 'Memory'}</div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    {#if !captureMode}
      <button
        on:click={startCapture}
        class="w-full py-3 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold rounded-xl transition"
      >
        + Capture Memory
      </button>
    {/if}

    {#if captureMode}
      <div class="bg-slate-900 rounded-2xl border border-slate-800 p-4 space-y-3">
        <h3 class="text-slate-100 font-medium">New Memory</h3>

        {#if mediaPreview}
          <div class="rounded-lg overflow-hidden">
            {#if mediaFile?.type.startsWith('video')}
              <video src={mediaPreview} controls class="w-full max-h-48" />
            {:else}
              <img src={mediaPreview} alt="Preview" class="w-full max-h-48 object-cover" />
            {/if}
          </div>
        {:else}
          <label class="block border-2 border-dashed border-slate-700 rounded-xl p-6 text-center cursor-pointer hover:border-cyan-500 transition">
            <input type="file" accept="image/*,video/*" class="hidden" on:change={onFileChange} />
            <div class="text-slate-400 text-sm">Tap to select photo or video</div>
          </label>
        {/if}

        <input
          type="text"
          bind:value={title}
          placeholder="Title"
          class="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm"
        />
        <textarea
          bind:value={description}
          placeholder="Description"
          rows="2"
          class="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 text-sm resize-none"
        ></textarea>

        <div class="flex gap-2">
          {#each ['public', 'friends', 'private'] as v}
            <button
              class="flex-1 py-2 rounded-lg text-sm font-medium transition {visibility === v ? 'bg-cyan-500 text-slate-950' : 'bg-slate-800 text-slate-400'}"
              on:click={() => (visibility = v as any)}
            >{v}</button>
          {/each}
        </div>

        <div>
          <label class="text-xs text-slate-400">Unlock radius: {unlockRadius}m</label>
          <input type="range" min="50" max="1000" step="50" bind:value={unlockRadius} class="w-full" />
        </div>

        {#if error}
          <div class="text-red-400 text-sm">{error}</div>
        {/if}

        <div class="flex gap-2">
          <button
            on:click={() => (captureMode = false)}
            class="flex-1 py-2 bg-slate-800 text-slate-300 rounded-lg text-sm"
          >Cancel</button>
          <button
            on:click={createMemory}
            disabled={creating}
            class="flex-1 py-2 bg-cyan-500 disabled:bg-slate-700 text-slate-950 rounded-lg text-sm font-medium"
          >{creating ? 'Saving...' : 'Save Memory'}</button>
        </div>
      </div>
    {/if}

    {#if loading}
      <div class="text-center text-slate-500 py-8">Loading...</div>
    {:else if memories.length === 0}
      <div class="text-center text-slate-500 py-8">
        <p>No memories yet.</p>
        <p class="text-sm mt-1">Capture your first memory to get started!</p>
      </div>
    {:else}
      <div class="space-y-3">
        {#each memories as m}
          <div class="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
            <div class="flex">
              <div class="w-20 h-20 flex-shrink-0">
                <img src={m.media_url} alt="" class="w-full h-full object-cover" />
              </div>
              <div class="flex-1 p-3 min-w-0">
                <div class="flex items-start justify-between">
                  <div>
                    <div class="text-slate-100 font-medium text-sm truncate">{m.title || 'Untitled'}</div>
                    {#if m.description}
                      <div class="text-slate-400 text-xs mt-0.5 line-clamp-2">{m.description}</div>
                    {/if}
                  </div>
                  <button on:click={() => deleteMemory(m.id)} class="text-slate-600 hover:text-red-400 text-xs ml-2">Delete</button>
                </div>
                <div class="flex items-center gap-2 mt-1.5">
                  <span class="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">{m.visibility}</span>
                  <span class="text-xs text-slate-500">{Math.round(m.unlock_radius_m)}m</span>
                </div>
              </div>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </main>
</div>
