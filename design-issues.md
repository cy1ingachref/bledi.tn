[#design] Design review issues verified on `fix/open-issues-parallel`:
- Login page dead links (#25) are not present; placeholders use `<button>` now.
- Swap control is a real button; keyboard access and `aria-label` are in place.
- Language choice is persisted via `bledi_lang` in localStorage.
- Board.svelte reduced-motion guard exists in `apps/web/src/app.css`.
- `design-issues.md` was stale as of main `589dd77`; current branch no longer matches the old claims.

Remaining design/auth work:
- `docs/auth-scheme.md` is still design-only; shared JWT consumption in Python is unimplemented.
- `/design-login` does not exist as a separate route; auth is at `/login`.
