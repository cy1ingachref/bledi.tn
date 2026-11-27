# Phase 3C Report — Docker/K8s + Python oracle verification + E2E route test

## Deliverables
- `services/routing/Dockerfile` — `rust:1-bookworm` builder → `debian:bookworm-slim`, binary + `data/transport_map_corrected.json`, EXPOSE 8081, curl healthcheck.
- `docker-compose.yml` — added `transit-routing` (context `.`, dockerfile `services/routing/Dockerfile`, `8081:8081`, `BLEDI_DATA_DIR=/app/data`, healthcheck). All existing services preserved.
- `k8s/namespace.yaml`, `k8s/routing.yaml`, `k8s/transit-api.yaml`, `k8s/web.yaml` — Deployment+Service each, namespace `bledi`, liveness/readiness probes (`/health`, `/api/v1/health`, `/`), resource requests/limits, no secrets.
- `scripts/phase3c_verify.py` + `docs/reports/data/phase3c_routes.json` (raw results).

## Verification (executed)
- `cargo check` in `services/routing`: PASS (2 pre-existing dead-code warnings).
- `docker compose config`: PASS; `--services` = db, accounts, transit, transit-routing, web.
- `docker compose build transit-routing`: NOT RUN — Docker daemon unavailable (`npipe:////./pipe/dockerDesktopLinuxEngine: file not found`; Docker Desktop not running). Honest blocker, not a config error.
- `python scripts/phase3c_verify.py`: PASS. Python oracle already running at `127.0.0.1:8000` (`/api/v1/health` 200, 7452 stations, 379 lines). Rust binary built and auto-started by the script on `:18081` (`/health` 200: 7444 stations, 379 lines, 35953 edges, `tokio::fs` fallback backend). Note: local `:8081` is the Vite dev server (HTML), correctly skipped by the script's JSON health check.

## Route table (real HTTP status codes; times/fares as returned)
| Route | Service/Objective | Status | Duration | Fare (DT) | Transfers | Modes |
|---|---|---|---|---|---|---|
| Tunis→Sousse | Python fastest | 200 | 232.9 min | 27.19 | 1 | train, taxi |
| Tunis→Sousse | Python cheapest | 200 | 366.8 min | 18.42 | 0 | louaj |
| Tunis→Sousse | Rust fastest | 200 | 142.7 min | 69.00 | 0 | — |
| Tunis→Sousse | Rust cheapest | 200 | 154.9 min | 18.00 | 0 | — |
| Tunis→Hammamet | Python fastest/cheapest | 200 | 139.9 min | 16.40 | 1 | train |
| Tunis→Hammamet | Rust fastest | 200 | 62.3 min | 52.00 | 0 | — |
| Tunis→Hammamet | Rust cheapest | 200 | 341.1 min | 17.00 | 1 | — |
| Bizerte→Tunis | Python fastest | 200 | 229.7 min | 11.29 | 0 | louaj, taxi |
| Bizerte→Tunis | Python cheapest | 200 | 689.2 min | 1.00 | 1 | bus |
| Bizerte→Tunis | Rust fastest | 200 | 94.8 min | 48.00 | 1 | — |
| Bizerte→Tunis | Rust cheapest | 200 | 91.8 min | 10.00 | 0 | — |
| Sousse→Monastir | Python fastest | 200 | 62.5 min | 6.88 | 0 | train |
| Sousse→Monastir | Python cheapest | 200 | 298.2 min | 0.00 | 0 | walk |
| Sousse→Monastir | Rust fastest | 200 | 24.4 min | 5.00 | 1 | — |
| Sousse→Monastir | Rust cheapest | 200 | 23.3 min | 4.00 | 0 | — |
| Tunis local | Python fastest | 200 | 70.9 min | 0.50 | 0 | bus |
| Tunis local | Python cheapest | 200 | 111.9 min | 0.00 | 0 | walk |
| Tunis local | Rust fastest | 200 | 11.7 min | 8.00 | 0 | — |
| Tunis local | Rust cheapest | 200 | 53.3 min | — | 0 | — |

Latency: Python 0.13–5.4 s/route; Rust 0.008–0.19 s/route (~10–100× faster).

## Problems found
1. **Python oracle durations look inflated for long hauls** (Tunis→Sousse 3h53 by train, Bizerte→Tunis cheapest 11h29, Sousse→Monastir cheapest = 4h58 walk). Likely waiting/transfer penalties + sparse line data, not real timetables.
2. **Rust fastest fares are implausible** (69 DT Tunis→Sousse, 52 DT Tunis→Hammamet) — per-km fare model over long distances; cheapest fares (18 DT, 17 DT) look sane. Fare model needs mode-specific caps/flat fares for train/louage.
3. **Rust and Python disagree on duration by 2–3×** (Rust systematically faster). Same graph data, different speed/wait/penalty tunables (`domain/tunables.py` vs `router.rs` constants). Needs a shared tunables table.
4. **Cheapest objectives degenerate to walk** in Python (0 DT, 298/112 min) — no minimum transit preference / walk cap by default.
5. **Station counts differ slightly** (Python 7452 vs Rust 7444) — Rust loader dedupes/normalises differently; 8 stations dropped.
6. Docker build not executed (daemon down); k8s manifests not applied (no cluster in scope) — config-validated only via compose.

## Final judgement: is this a good fastest/cheapest/preference map?
- **Fastest**: usable as a *relative* ordering (Rust is fast and consistent), but absolute times are not trustworthy — Python overestimates long hauls, Rust likely underestimates (no congestion/schedule). Good enough for "which corridor" decisions, not for departure planning.
- **Cheapest**: Rust cheapest is the most believable output (flat-ish fares, sane ordering); Python cheapest is broken by walk degeneracy. Fix by capping walk in cheapest or excluding pure-walk itineraries.
- **Preference (mode filters)**: both APIs accept mode include/exclude (`modes_include`/`allowed_modes`), so preference routing is supported structurally; not exercised in this run beyond defaults.
- **Verdict**: solid prototype map for corridor/mode choice, **not yet** a reliable fastest/cheapest trip planner. Priority fixes: (1) reconcile tunables between Rust/Python, (2) mode-specific fare model, (3) walk cap on cheapest, (4) re-run this script and diff again. Docker/K8s packaging is ready pending a running daemon/cluster.
