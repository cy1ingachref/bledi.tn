<script lang="ts"></script>

<span class="spin" aria-hidden="true"></span>

<style>
  .spin {
    width: 14px; height: 14px; flex-shrink: 0;
    border: 2px solid color-mix(in srgb, var(--on-accent) 35%, transparent);
    border-top-color: var(--on-accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
