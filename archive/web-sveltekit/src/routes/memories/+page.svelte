<script>
  import { onMount, onDestroy } from 'svelte';
  import MapView from '$lib/MapView.svelte';
  import { resolve } from '$app/paths';
  import { ui } from '$lib/ui.svelte.js';
  import { fetchMedia } from '$lib/api.js';
  import { listMemories, createMemory, deleteMemory, fetchNearbyMemories } from '$lib/memories.js';
  import { goto } from '$app/navigation';

  const copy = {
    fr: {
      title: 'Mémoires géolocalisées',
      sub: 'Déposez un souvenir ou explorez les environs.',
      back: 'Retour à la carte',
      loginRequired: 'Connectez-vous pour déposer ou voir vos mémoires.',
      loginBtn: 'Se connecter',
      newTitle: 'Nouveau souvenir',
      placeTitle: 'Titre',
      placeDesc: 'Description',
      lat: 'Latitude',
      lon: 'Longitude',
      radius: 'Rayon de déverrouillage (m)',
      visibility: 'Visibilité',
      public: 'Public',
      friends: 'Amis uniquement',
      private: 'Privé',
      photo: 'Photo (obligatoire)',
      submit: 'Déposer la mémoire',
      myMemories: 'Mes mémoires',
      nearby: 'Mémoires à proximité',
      unlock: 'Déverrouiller',
      delete: 'Supprimer',
      noPhoto: 'Choisir une photo',
      radiusHint: 'La photo ne sera visible qu’aux utilisateurs situés dans ce rayon.'
    },
    ar: {
      title: 'الذكريات الجغرافية',
      sub: 'اترك ذكرى أو استكشف محيطك.',
      back: 'العودة إلى الخريطة',
      loginRequired: 'تسجيل الدخول مطلوب لإضافة أو عرض الذكريات.',
      loginBtn: 'تسجيل الدخول',
      newTitle: 'ذكرى جديدة',
      placeTitle: 'العنوان',
      placeDesc: 'الوصف',
      lat: 'خط العرض',
      lon: 'خط الطول',
      radius: 'نصف قطر الفتح (متر)',
      visibility: 'الخصوصية',
      public: 'عام',
      friends: 'الأصدقاء فقط',
      private: 'خاص',
      photo: 'صورة (مطلوبة)',
      submit: 'إضافة الذكرى',
      myMemories: 'ذكرياتي',
      nearby: 'الذكريات القريبة',
      unlock: 'فتح',
      delete: 'حذف',
      noPhoto: 'اختر صورة',
      radiusHint: 'الصورة تظهر فقط للمستخدمين ضمن هذا النطاق.'
    },
    en: {
      title: 'Geo Memories',
      sub: 'Drop a memory or explore nearby.',
      back: 'Back to map',
      loginRequired: 'Log in to post or view your memories.',
      loginBtn: 'Log in',
      newTitle: 'New Memory',
      placeTitle: 'Title',
      placeDesc: 'Description',
      lat: 'Latitude',
      lon: 'Longitude',
      radius: 'Unlock Radius (m)',
      visibility: 'Visibility',
      public: 'Public',
      friends: 'Friends only',
      private: 'Private',
      photo: 'Photo (required)',
      submit: 'Drop Memory',
      myMemories: 'My Memories',
      nearby: 'Nearby Memories',
      unlock: 'Unlock',
      delete: 'Delete',
      noPhoto: 'Choose a photo',
      radiusHint: 'Photo is only revealed to users within this radius.'
    }
  };

  const t = $derived(copy[ui.lang]);

  let auth = $state(null);
  let memories = $state([]);
  let nearby = $state([]);
  let loading = $state(true);
  let error = $state('');

  const fmtCoord = (v) =>
    typeof v === 'number' && Number.isFinite(v) ? v.toFixed(4) : '—';

  // The media endpoint needs the caller's token, so the photos are fetched as bytes and
  // shown through object URLs.
  let photos = $state({});
  let objectUrls = [];

  // New memory form state
  let title = $state('');
  let description = $state('');
  let lat = $state('36.8065');
  let lon = $state('10.1815');
  let unlockRadiusM = $state('200');
  let visibility = $state('public');
  let photoFile = $state(null);
  let submitting = $state(false);

  onMount(() => {
    try {
      const stored = localStorage.getItem('bledi_auth');
      if (stored) {
        auth = JSON.parse(stored);
      }
    } catch (err) {
      console.error('Auth parse failed', err);
      localStorage.removeItem('bledi_auth');
      goto(resolve('/login'));
    }

    loadData();
  });

  onDestroy(() => {
    objectUrls.forEach((url) => URL.revokeObjectURL(url));
    objectUrls = [];
  });

  /** Fetches the photos the caller may see and turns them into object URLs. */
  async function loadPhotos(list) {
    if (!auth?.token) return;
    await Promise.all(
      list.map(async (m) => {
        if (!m.media_url || photos[m.media_url]) return;
        try {
          const blob = await fetchMedia(auth.token, m.media_url);
          const url = URL.createObjectURL(blob);
          objectUrls.push(url);
          photos = { ...photos, [m.media_url]: url };
        } catch (err) {
          console.warn('Memory photo load failed', err);
          // The server refused this one: the memory is listed without a photo.
        }
      })
    );
  }

  async function loadData() {
    loading = true;
    error = '';
    try {
      if (auth?.token) {
        memories = await listMemories(auth.token);
        // The nearby ones are summaries: their photos stay locked until they are unlocked.
        nearby = await fetchNearbyMemories(auth.token, { lat: 36.8065, lon: 10.1815, radius_m: 50000 });
        await loadPhotos(memories);
      }
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!auth?.token || !photoFile) return;
    submitting = true;
    error = '';

    try {
      await createMemory(
        auth.token,
        {
          title,
          description,
          lat,
          lon,
          unlock_radius_m: unlockRadiusM,
          visibility
        },
        photoFile
      );
      title = '';
      description = '';
      photoFile = null;
      await loadData();
    } catch (e) {
      error = e.message;
    } finally {
      submitting = false;
    }
  }

  async function handleDelete(id) {
    if (!auth?.token) return;
    try {
      await deleteMemory(auth.token, id);
      await loadData();
    } catch (e) {
      error = e.message;
    }
  }

  // The map shows the caller's own memories and the ones nearby. A memory can be in both
  // lists, so it is only marked once.
  const mapMemories = $derived.by(() => {
    const seen = {};
    return [...memories, ...nearby].filter((m) => {
      if (m.lat == null || m.lon == null || seen[m.id]) return false;
      seen[m.id] = true;
      return true;
    });
  });
</script>

<svelte:head>
  <title>bledi.tn - {t.title}</title>
</svelte:head>

<main class="scene" dir={ui.lang === 'ar' ? 'rtl' : 'ltr'}>
  <header class="topbar">
    <div class="brand">
      <a href={resolve('/')}>bledi<span>.tn</span></a>
      <span class="sep">/</span>
      <h1>{t.title}</h1>
    </div>
    <a class="back-btn" href={resolve('/')}>{t.back}</a>
  </header>

  <div class="content">
    {#if !auth?.token}
      <div class="card login-prompt">
        <p>{t.loginRequired}</p>
        <a class="btn primary" href={resolve('/login')}>{t.loginBtn}</a>
      </div>
    {:else}
      <div class="map-wrap">
        <MapView
          memories={mapMemories}
          photos={photos}
          mediaToken={auth.token}
          rtl={ui.lang === 'ar'}
          mapReady={true}
        />
      </div>

      <div class="grid">
        <!-- Create Form -->
        <div class="card">
          <h2>{t.newTitle}</h2>
          {#if error}
            <div class="error">{error}</div>
          {/if}
          <form onsubmit={handleSubmit} class="memory-form">
            <label class="field">
              <span>{t.placeTitle}</span>
              <input type="text" bind:value={title} required />
            </label>
            <label class="field">
              <span>{t.placeDesc}</span>
              <textarea bind:value={description} rows="2"></textarea>
            </label>
            <div class="row">
              <label class="field">
                <span>{t.lat}</span>
                <input type="number" step="any" bind:value={lat} required />
              </label>
              <label class="field">
                <span>{t.lon}</span>
                <input type="number" step="any" bind:value={lon} required />
              </label>
            </div>
            <div class="row">
              <label class="field">
                <span>{t.radius}</span>
                <input type="number" bind:value={unlockRadiusM} required />
              </label>
              <label class="field">
                <span>{t.visibility}</span>
                <select bind:value={visibility}>
                  <option value="public">{t.public}</option>
                  <option value="friends">{t.friends}</option>
                  <option value="private">{t.private}</option>
                </select>
              </label>
            </div>
            <p class="hint">{t.radiusHint}</p>

            <label class="field">
              <span>{t.photo}</span>
              <input
                type="file"
                accept="image/jpeg,image/png"
                required
                onchange={(e) => (photoFile = e.target.files[0] ?? null)}
              />
            </label>
            {#if photoFile}
              <p class="hint">{photoFile.name}</p>
            {/if}

            <button class="btn primary submit-btn" disabled={submitting || !photoFile}>
              {submitting ? '...' : t.submit}
            </button>
          </form>
        </div>

        <!-- My Memories & Nearby -->
        <div class="list-section">
          <div class="card">
            <h2>{t.myMemories}</h2>
            {#if loading}
              <p class="muted">...</p>
            {:else if memories.length === 0}
              <p class="muted">-</p>
            {:else}
              <ul class="mem-list">
                {#each memories as m}
                  <li>
                    <div class="mem-info">
                      {#if photos[m.media_url]}
                        <img class="thumb" src={photos[m.media_url]} alt={m.title || 'Memory'} />
                      {/if}
                      <strong>{m.title || 'Untitled'}</strong>
                      <span class="meta">{m.visibility} • {m.unlock_radius_m}m</span>
                    </div>
                    <button class="btn danger sm" onclick={() => handleDelete(m.id)}>{t.delete}</button>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>

          <div class="card">
            <h2>{t.nearby}</h2>
            {#if nearby.length === 0}
              <p class="muted">-</p>
            {:else}
              <ul class="mem-list">
                {#each nearby as m}
                  <li>
                    <div class="mem-info">
                      <strong>{m.title || 'Untitled'}</strong>
                      <span class="meta">{m.visibility} • {fmtCoord(m.lat)}, {fmtCoord(m.lon)}</span>
                    </div>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </div>
</main>

<style>
  .scene {
    min-height: 100dvh; background: radial-gradient(ellipse at 50% 35%, #214559, #0f2230 72%);
    color: #1b3a4b; font-family: 'Courier Prime', 'Readex Pro Variable', monospace;
    padding: 24px; box-sizing: border-box;
  }
  .topbar {
    display: flex; justify-content: space-between; align-items: center;
    max-width: 1000px; margin: 0 auto 24px; background: #c9dde6;
    padding: 12px 20px; border-radius: 6px; box-shadow: 0 4px 12px #0004;
  }
  .brand { display: flex; align-items: baseline; gap: 8px; }
  .brand a { color: #1b3a4b; text-decoration: none; font-weight: 700; font-size: 1.2rem; }
  .brand span span { color: var(--red, #a3262a); }
  .sep { color: #6f8c9b; }
  .topbar h1 { margin: 0; font-size: 1rem; font-weight: normal; color: #3b6277; }
  .back-btn { background: #1b3a4b; color: #c9dde6; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.9rem; }
  .back-btn:hover { background: #2a4252; }

  .content { max-width: 1000px; margin: 0 auto; }
  .card {
    background: #c9dde6; border-radius: 6px; padding: 24px; box-shadow: 0 8px 20px #0005;
    margin-bottom: 20px;
  }
  .login-prompt { text-align: center; padding: 48px; }

  .map-wrap {
    position: relative; height: 42dvh; min-height: 280px; margin-bottom: 20px;
    border-radius: 6px; overflow: hidden; box-shadow: 0 8px 20px #0005;
  }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }

  h2 { margin-top: 0; font-size: 1.1rem; border-bottom: 2px dashed #8aa0ab; padding-bottom: 8px; margin-bottom: 16px; }

  .memory-form { display: grid; gap: 14px; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 0.85rem; font-weight: 700; }
  .field input, .field select, .field textarea {
    padding: 8px; border: 1px solid #8aa0ab; border-radius: 4px; background: #fff;
    font: inherit; font-weight: normal;
  }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .hint { font-size: 0.75rem; color: #4a6b7c; margin: 0; }
  .error { background: #fde8e8; color: #9b1c1c; padding: 8px 12px; border-radius: 4px; font-size: 0.85rem; margin-bottom: 12px; }

  .btn {
    padding: 10px 16px; border: 0; border-radius: 4px; font: inherit; font-weight: 700; cursor: pointer; text-decoration: center; display: inline-block;
  }
  .btn.primary { background: var(--ink, #1b3a4b); color: #c9dde6; }
  .btn.primary:hover { background: #2a4252; }
  .btn.primary:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn.danger { background: #9b1c1c; color: #fff; padding: 4px 8px; font-size: 0.8rem; }
  .btn.danger:hover { background: #771515; }
  .submit-btn { width: 100%; margin-top: 8px; }

  .muted { color: #6f8c9b; font-style: italic; font-size: 0.9rem; }
  .mem-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; }
  .mem-list li {
    background: #ffffff60; padding: 12px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; gap: 12px;
  }
  .mem-info { display: grid; gap: 2px; min-width: 0; }
  .mem-info strong { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meta { font-size: 0.75rem; color: #4a6b7c; }
  .thumb {
    width: 100%; max-width: 220px; aspect-ratio: 4 / 3; object-fit: cover;
    border-radius: 4px; display: block; margin-bottom: 4px;
  }
</style>
