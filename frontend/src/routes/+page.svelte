<script lang="ts">
  import { onMount } from "svelte";

  onMount(() => {
    window.location.replace("/map");
  });
</script>

<div class="flex items-center justify-center h-screen bg-slate-950 text-slate-400">
  <p>Redirecting to map...</p>
</div>
