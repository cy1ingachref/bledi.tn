[#design] Design review status on `fix/open-issues-parallel` @ 333b867:
- Login dead links (#25): no `href="#"` placeholders remain.
- Swap control (#27): real button, keyboard reachable.
- Keyboard/markers (#55): MapView markers no longer use `keyboard:false`.
- Memory markers a11y (#55): popups built from DOM nodes with `alt` text.
- Empty state a11y (#27): route unavailable state is a button.
- Bare catch logging (#28): route/MapView/memories catch blocks log errors.
- Board dead code (#52): removed `Board.svelte` and replaced with inline markup.
- Loading state (#49): station fetch always clears `loading` in `finally`.

Remaining design/auth/docs work:
- `docs/auth-scheme.md` is still design-only; shared JWT consumption in Python is unimplemented.
- `/design-login` does not exist as a separate route; auth is at `/login`.
- Web test coverage is still minimal; `npm run test` now runs focused route-mode tests.
