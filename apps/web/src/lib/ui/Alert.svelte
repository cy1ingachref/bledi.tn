<script lang="ts">
  import Icon from "$lib/ui/Icon.svelte";

  let { message, warn = false, size = 15 }: { message: string; warn?: boolean; size?: number } = $props();
</script>

<div class="alert" class:warn role={warn ? "status" : "alert"}>
  <Icon name="alert" {size} /><span>{message}</span>
</div>

<style>
  .alert {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 10px 13px;
    border: 1px solid rgba(255, 61, 129, 0.32);
    border-radius: 14px;
    background: rgba(255, 61, 129, 0.1);
    color: #ffb3cc;
    font-size: 12px; line-height: 1.45;
  }
  .alert.warn { border-color: rgba(255, 196, 0, 0.32); background: rgba(255, 196, 0, 0.1); color: #ffd98a; }
  .alert :global(svg) { flex-shrink: 0; margin-top: 1px; }
</style>
