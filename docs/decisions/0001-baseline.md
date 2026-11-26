# 0001 — Baseline (T0.1 / T0.2)

Date: 2026-11-26
Repo: `C:\Users\cy1in\bledi.tn`, branch `main`, HEAD `c11db41`
Tag: `baseline-2026-11`

This record is the Phase 0 baseline required by `bledi-agent-brief.md` T0.1.
All results below were produced by real commands in this session; nothing is
inferred from documentation alone.

## 1. Brief vs. actual repository (brief §0 rule 1 — verified, not assumed)

The attached `bledi-agent-brief.md` §1 describes an older state of the project.
The checked-out repo differs materially. These are observations, not changes.

| Brief §1 assumption | Actual state (verified 2026-11-26) |
|---|---|
| FastAPI backend `src/backend/app/main.py`, `routing.py` | `services/transit` (FastAPI, factory `create_app`), `services/routing` (Rust axum), `services/accounts` (Rust axum + sqlx/Postgres) |
| Single-file Leaflet UI `frontend/index.html` | React + Vite app `apps/web-react` is the canonical frontend (`:8080`). SvelteKit `apps/web` is still present and tracked but is the legacy app; `apps/web-new` is absent. |
| 232 lines, 1,711 stations | ~7,450 stations / 379 lines (per run-bledi-app skill and seed load) |
| Basemap changed to Maptoolkit Dark | In-flight uncommitted MapLibre migration on `main` (see §3) |
| Live tracking service absent | Confirmed absent |
| Docker compose at repo root | Confirmed `docker-compose.yml` at root: services `db`, `accounts`, `transit`, `transit-routing`, `web` |

The brief's §2–§8 target layout (`services/transit-router`, `apps/web`,
`contracts/`, `infra/docker-compose.yml`, gateway) is a *target*, not the
current layout. Tasks referring to those paths must be adapted before execution.

**Decision:** keep the brief as the intention document; record divergence here
rather than rewriting the brief in this baseline task. A dedicated reconciliation
task is still open.

## 2. Toolchain (verified)

- Python 3.11.15; pytest 9.1.1; ruff 0.16.0 ( Hermes venv )
- cargo 1.99.0; node 22.17.0; Docker CLI 29.9.3
- `apps/web-react/node_modules` present; `vitest` declared in `package.json`
  (`"test": "vitest run"`) but NOT installed in `node_modules`.

## 3. Test results (real command output)

### Frontend (`apps/web-react`)
- `node node_modules/typescript/bin/tsc --noEmit` → **exit 0** (clean).
- `vitest run` → **not runnable**: `Cannot find module .../node_modules/vitest/vitest.mjs`
  (also `require.resolve('vitest')` → MODULE_NOT_FOUND). `node_modules/.vite/vitest`
  is a Vite cache dir, not the package. Test files exist: `src/catalog.test.ts`,
  `src/catalogPath.test.ts`, `src/labels.test.ts`, `src/welcome.test.ts`.
  Resolution: install vitest as a dev dependency (separate task; do not mutate
  deps in the middle of the uncommitted MapLibre work).
- Four test files exist but could not be executed this session — recorded as a
  failure to run, not a pass.

### FastAPI backend (`services/transit`)
- `PYTHONPATH=src python -m pytest tests -q --disable-warnings` →
  **191 passed, 1 warning in 35.57 s (exit 0)**.
  Note: the repo's `tests/` at root contains only stale `.pyc` caches; the live
  suite is `services/transit/tests/`.

### Rust routing (`services/routing`)
- `cargo test --manifest-path services/routing/Cargo.toml` →
  **3 passed, 0 failed (exit 0)**. Warnings only: unused constants
  `FEWEST_TRANSFERS_PENALTY_SEC`, `MAX_DIRECT_WALK_M`, unused `Station.name/mode`
  and `Graph.mode_of_line` fields.

### Rust accounts (`services/accounts`)
- `cargo test --manifest-path services/accounts/Cargo.toml` →
  unit/doc tests pass (0 tests), **`bledi-postgres` integration test `stores`:
  6 failed, 0 passed (exit 101)**.
  All 6 failures are `DATABASE_URL must point at a test database: NotPresent`
  (env var unset). The tests call `MIGRATOR.run()` and insert `@itest.invalid`
  rows without cleanup, so they need a disposable test DB. A local Postgres is
  listening on :5432, but pointing these tests at it would migrate/pollute an
  unknown database — deliberately not done. This is an environment prerequisite,
  not a code regression.

### Lint
- `python -m ruff check services/transit` → **exit 1, 95 errors**
  (57 auto-fixable, 24 more with unsafe fixes). Pre-existing lint debt; no fixes
  applied in baseline.

### Compose / runtime (re-verified 2026-11-26 later session)
- `docker compose config -q` → **exit 0** (file parses).
- Docker Desktop was installed but not running; launched it, engine 29.9.3 (linux).
- `docker compose up -d --build` → **all 5 services up and healthy**
  (`db`, `accounts`, `transit`, `transit-routing`, `web`).
- Host verification: `http://127.0.0.1:8080/` → 200, React shell
  (`<div id="root">`, title `bledi.tn — Itinéraires transport Tunis`);
  `http://127.0.0.1:8080/api/v1/health` → 200 with
  `stations_count=7452, lines_count=379`; `http://127.0.0.1:8081/health`
  → 200 with Rust graph stats. T0.1's "transit /health healthcheck verified"
  is now **satisfied** (via the corrected `/api/v1/health` probe).
- Browser E2E (Playwright): React app renders MapLibre dark basemap with
  Maptoolkit logo + OSM attribution; zero console errors/warnings; clicking
  "Tunis Marine → La Marsa" triggers `/api/v1/route/plan` → 200 and displays
  Bus + Train itineraries with times/fares/steps and A/B markers.
- Fixes required to get there (all in working tree, uncommitted):
  - `docker-compose.yml`: `web.build` repointed `apps/web` → `apps/web-react`
    (React is canonical; brief's Svelte path was stale).
  - `docker-compose.yml`: transit healthcheck `/health` → `/api/v1/health`
    (the code only serves the latter; `/health` was 404).
  - `services/accounts/docker/init-db.sh`: CRLF → LF (`/bin/sh^M: bad
    interpreter` broke db init on Linux); `.gitattributes` now enforces
    `*.sh text eol=lf`. The missing `accounts` role/db was created in the
    already-initialized local db container (no volumes destroyed).
  - `apps/web-react/Dockerfile` + `nginx.conf` created for the React build:
    multi-stage node→nginx, `/api/` → transit, auth paths → accounts,
    `/routing/` → Rust, SPA fallback; `mjs` MIME type added to nginx;
    CSP allows same-origin module workers (`worker-src 'self' blob:`) and
    Google Fonts hosts. Without these the MapLibre worker failed to load.

### Earlier (first-pass) note, superseded
- `docker compose ps` initially → daemon not reachable; healthchecks could not
  be verified live. Superseded by the re-verification above.

## 4. Uncommitted work in tree (do not clobber)

`git status --short` at baseline shows modified:
`apps/web-react/package.json` (+ `maplibre-gl@^6.19.0`,
`@maptoolkit/maplibre-logo-control@^1.1.2`), `package-lock.json`, `catalog.ts`,
`catalogPath.test.ts`, `components/LedBoard.tsx`, `components/MapView.tsx`
(+326/-…), `index.css`; untracked `apps/web-react/src/maplibre/setup.ts`,
`apps/web-react/src/vite-env.d.ts`. This looks like an in-flight Phase 3
(MapLibre) migration. No baseline command modified these files.

## 5. Acceptance status for T0.1 / T0.2

- Tests run and results documented: **yes** (with one runnable-blocker recorded:
  vitest not installed; accounts tests blocked until run against a disposable DB).
- `transit /health` healthcheck verified: **yes** (via `/api/v1/health`, now the
  compose healthcheck; stack up and healthy — see §3 Compose re-verification).
- Tag `baseline-2026-11` created: **yes** (see git tag).

## 6. Open items carried forward

1. Install vitest (dev dependency) and run the 4 frontend test files.
2. Provide a disposable Postgres + `DATABASE_URL` and re-run accounts store tests.
3. Start Docker Desktop, `docker compose up`, and verify all healthchecks incl. transit `/health`.
4. Fix or triage the 95 ruff errors (Phase 1 CI gate T1.8 depends on this).
5. Reconcile brief §1/§2–§8 paths with the real monorepo layout.
6. Owner-decision gates still unresolved (brief §0 rule 7): data license (T1.5/1.6),
   pilot region (T1.7), tracking stack (§4). Do not guess.
