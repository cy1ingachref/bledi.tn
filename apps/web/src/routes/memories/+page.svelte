<script>
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { getMemories, addMemory, deleteMemory } from '$lib/memories.js';

  // --- camera state ---
  let videoEl = $state(null);
  let stream = $state(null);
  let cameraError = $state('');
  let cameraActive = $state(false);
  let cameraStarting = $state(false);

  // --- captured photo ---
  let capturedDataUrl = $state('');

  // --- form state ---
  let title = $state('');
  let description = $state('');
  let saving = $state(false);

  // --- gallery state ---
  let memories = $state([]);
  let loading = $state(true);

  // --- load saved memories on mount ---
  onMount(async () => {
    try {
      memories = await getMemories();
    } catch (e) {
      console.error('Failed to load memories', e);
    }
    loading = false;
  });

  // --- camera ---
  async function startCamera() {
    cameraError = '';
    cameraStarting = true;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        cameraError = 'Camera API is not available. Make sure you are on HTTPS or localhost.';
        cameraStarting = false;
        return;
      }
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
      if (videoEl) {
        videoEl.srcObject = stream;
        await videoEl.play();
        cameraActive = true;
      }
    } catch (err) {
      cameraActive = false;
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        cameraError =
          'Camera permission was denied. Please allow camera access in your browser settings to take photos.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        cameraError = 'No camera was found on this device.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        cameraError = 'The camera is already in use by another application.';
      } else if (err.name === 'SecurityError') {
        cameraError = 'Camera access requires a secure (HTTPS) connection.';
      } else {
        cameraError = 'Could not access the camera. Please try again.';
      }
    }
    cameraStarting = false;
  }

  function stopCamera() {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
    }
    cameraActive = false;
  }

  function capturePhoto() {
    if (!videoEl || !cameraActive) return;
    const canvas = document.createElement('canvas');
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoEl, 0, 0);
    capturedDataUrl = canvas.toDataURL('image/jpeg', 0.85);
    stopCamera();
  }

  function retakePhoto() {
    capturedDataUrl = '';
    startCamera();
  }

  // --- save memory ---
  async function saveMemory() {
    if (!capturedDataUrl || !title.trim()) return;
    saving = true;
    cameraError = '';
    try {
      await addMemory({
        title: title.trim(),
        description: description.trim(),
        photoDataUrl: capturedDataUrl,
        lat: null,
        lon: null,
        createdAt: new Date().toISOString(),
      });
      memories = await getMemories();
      // reset form
      title = '';
      description = '';
      capturedDataUrl = '';
    } catch (e) {
      console.error('Failed to save memory', e);
      cameraError = 'Failed to save memory. Please try again.';
    }
    saving = false;
  }

  // --- delete memory ---
  async function handleDelete(id) {
    try {
      await deleteMemory(id);
      memories = memories.filter((m) => m.id !== id);
    } catch (e) {
      console.error('Failed to delete memory', e);
    }
  }

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return '';
    }
  }

  onDestroy(() => {
    stopCamera();
  });
</script>

<svelte:head>
  <title>Memories — bledi.tn</title>
</svelte:head>

<main class="memories-page">
  <header class="top-bar">
    <button class="back-btn" onclick={() => goto('/')} aria-label="Back to home">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>
    </button>
    <h1>Memories</h1>
    <span class="spacer"></span>
  </header>

  <section class="camera-section">
    {#if cameraError}
      <div class="error-banner" role="alert">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <p>{cameraError}</p>
      </div>
    {/if}

    {#if !capturedDataUrl}
      <div class="camera-viewport">
        {#if cameraActive}
          <video bind:this={videoEl} autoplay playsinline muted class="video-preview"></video>
        {:else}
          <div class="camera-placeholder">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
            <p>Camera is off</p>
          </div>
        {/if}
      </div>

      <div class="camera-controls">
        {#if !cameraActive}
          <button class="btn primary" onclick={startCamera} disabled={cameraStarting}>
            {cameraStarting ? 'Starting…' : 'Start Camera'}
          </button>
        {:else}
          <button class="btn primary" onclick={capturePhoto}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
            Capture
          </button>
        {/if}
      </div>
    {:else}
      <div class="captured-viewport">
        <img src={capturedDataUrl} alt="Captured" class="captured-photo" />
      </div>

      <form class="memory-form" onsubmit={(e) => { e.preventDefault(); saveMemory(); }}>
        <div class="field">
          <label for="mem-title">Title</label>
          <input id="mem-title" type="text" bind:value={title} placeholder="Name this memory…" required />
        </div>
        <div class="field">
          <label for="mem-desc">Description</label>
          <textarea id="mem-desc" bind:value={description} placeholder="What happened here? (optional)" rows="3"></textarea>
        </div>
        <div class="form-actions">
          <button type="button" class="btn ghost" onclick={retakePhoto}>Retake</button>
          <button type="submit" class="btn primary" disabled={saving || !title.trim()}>
            {saving ? 'Saving…' : 'Save Memory'}
          </button>
        </div>
      </form>
    {/if}
  </section>

  <section class="gallery-section">
    <h2>Your Memories</h2>
    {#if loading}
      <p class="muted">Loading memories…</p>
    {:else if memories.length === 0}
      <div class="empty-state">
        <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
        <p>No memories yet. Take a photo above to get started!</p>
      </div>
    {:else}
      <div class="gallery-grid">
        {#each memories as mem (mem.id)}
          <article class="memory-card">
            <img src={mem.photoDataUrl} alt={mem.title} class="memory-photo" />
            <div class="memory-info">
              <h3>{mem.title}</h3>
              <time datetime={mem.createdAt}>{formatDate(mem.createdAt)}</time>
              {#if mem.description}
                <p class="desc">{mem.description}</p>
              {/if}
              <button class="delete-btn" onclick={() => handleDelete(mem.id)} aria-label="Delete memory">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                Delete
              </button>
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </section>
</main>

<style>
  .memories-page {
    min-height: 100dvh;
    background: var(--ink);
    color: var(--paper);
    display: flex;
    flex-direction: column;
  }

  /* --- top bar --- */
  .top-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: var(--ink);
    border-bottom: 1px solid #ffffff18;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  .top-bar h1 {
    margin: 0;
    font-size: 1.3rem;
    font-weight: 700;
  }
  .top-bar h1::after {
    content: '';
  }
  .back-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border: 1px solid #ffffff28;
    border-radius: 10px;
    background: transparent;
    color: var(--paper);
  }
  .back-btn:hover {
    background: var(--sea);
    border-color: var(--sea);
  }
  .spacer {
    flex: 1;
  }

  /* --- camera section --- */
  .camera-section {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    border-bottom: 1px solid #ffffff18;
  }

  .camera-viewport {
    width: 100%;
    aspect-ratio: 4 / 3;
    border-radius: 14px;
    overflow: hidden;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .video-preview {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .camera-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    color: var(--muted);
  }

  .camera-controls {
    display: flex;
    gap: 10px;
    justify-content: center;
  }

  .captured-viewport {
    width: 100%;
    border-radius: 14px;
    overflow: hidden;
  }
  .captured-photo {
    width: 100%;
    display: block;
  }

  /* --- buttons --- */
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    border-radius: 12px;
    font-size: 0.95rem;
    font-weight: 600;
    border: 1px solid transparent;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .btn.primary {
    background: var(--amber);
    color: var(--ink);
    border-color: var(--amber);
  }
  .btn.primary:hover:not(:disabled) {
    filter: brightness(1.1);
  }
  .btn.ghost {
    background: transparent;
    color: var(--paper);
    border-color: #ffffff38;
  }
  .btn.ghost:hover {
    background: #ffffff14;
  }

  /* --- error banner --- */
  .error-banner {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 14px;
    border-radius: 12px;
    background: #d7261e22;
    border: 1px solid #d7261e66;
    color: #ff8a80;
  }
  .error-banner svg {
    flex-shrink: 0;
    margin-top: 2px;
  }
  .error-banner p {
    margin: 0;
    font-size: 0.9rem;
  }

  /* --- form --- */
  .memory-form {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .field label {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--sea);
  }
  .field input,
  .field textarea {
    width: 100%;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid #ffffff28;
    background: #ffffff0a;
    color: var(--paper);
    font: inherit;
    resize: vertical;
  }
  .field input::placeholder,
  .field textarea::placeholder {
    color: #ffffff50;
  }
  .field input:focus,
  .field textarea:focus {
    outline: 2px solid var(--sea);
    outline-offset: 1px;
  }
  .form-actions {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
  }

  /* --- gallery --- */
  .gallery-section {
    padding: 16px;
    flex: 1;
  }
  .gallery-section h2 {
    margin: 0 0 14px;
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--paper);
  }
  .muted {
    color: var(--muted);
    font-size: 0.9rem;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 40px 20px;
    color: var(--muted);
    text-align: center;
  }
  .empty-state p {
    margin: 0;
    font-size: 0.95rem;
  }

  .gallery-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 14px;
  }
  .memory-card {
    background: #ffffff08;
    border: 1px solid #ffffff14;
    border-radius: 14px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .memory-photo {
    width: 100%;
    aspect-ratio: 4 / 3;
    object-fit: cover;
    display: block;
  }
  .memory-info {
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .memory-info h3 {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--paper);
  }
  .memory-info time {
    font-size: 0.78rem;
    color: var(--sea);
    font-variant-numeric: tabular-nums;
  }
  .memory-info .desc {
    margin: 0;
    font-size: 0.85rem;
    color: var(--muted);
    line-height: 1.4;
  }
  .delete-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 6px;
    padding: 6px 12px;
    border-radius: 8px;
    border: 1px solid #d7261e55;
    background: #d7261e18;
    color: #ff8a80;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    align-self: flex-start;
  }
  .delete-btn:hover {
    background: #d7261e33;
  }

  @media (min-width: 800px) {
    .gallery-grid {
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    }
  }
</style>