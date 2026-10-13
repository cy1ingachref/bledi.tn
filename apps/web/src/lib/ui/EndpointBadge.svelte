<script lang="ts">
  let { end }: { end: "a" | "b" } = $props();
</script>

<span class="badge {end}">{end.toUpperCase()}</span>

<style>
  .badge {
    display: grid; place-items: center;
    width: 17px; height: 17px; flex-shrink: 0;
    border-radius: 50%;
    font-size: 9px; font-weight: 800;
    color: #05020e;
  }
  .badge.a { background: #22d3ee; }
  .badge.b { background: #f472b6; }
</style>
