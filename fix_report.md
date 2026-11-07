# Fix Report — tunables/fares, shared IDs, re-verify

Verified by execution (cargo check, phase3c_verify.py, reconcile script). No commits.

## Fix 1 — tunables/fares reconciled
- data/shared_tunables.json created as single source of truth (speeds, wait per mode Train600 Metro300 Bus600, transfer 180s, fare caps Train/Rail 15DT Louage/Louaj 20DT, walk caps 900m edge/2000m access/1000m direct/120min pure-walk)
- data/tunables_reconcile.json: status aligned, 0 mismatches (AST/regex parse of Python + Rust)
- scripts/reconcile_tunables.py: runs exit 0
- Python domain/tunables.py + fares.py updated (louage speed 45, rail/rural/tram waits, FARE_CAPS per boarding)
- Rust services/routing/src/graph.rs + router.rs updated: WAIT_S_BY_MODE, FARE_CAP_DT, marginal_fare per boarding (was per edge => 69DT bug), per-mode wait (was flat 300s)

## Fix 2 — shared station IDs disambiguated
- data/station_disambiguation.json: mapping original id -> disambiguated ids per mode
- data/seed_disambiguated.json created (original seed unchanged)
- scripts/fix_shared_ids.py: reproduces transformation
- Main case: les_salines (train 36.078,8.964) split to les_salines__train / les_salines__bus (Rades) fixing bus_708_17 142km teleport legs

## Fix 3 — verify rerun
- cargo check services/routing: PASS
- Rust /health on :18081: 200 {stations 7444, lines 379, edges 35953, io_backend tokio::fs fallback}
- scripts/phase3c_verify.py: PASS (exit 0). Rust fastest fares now capped/sane: Tunis->Sousse 15.0DT (was 69.0), Tunis->Hammamet 10.0DT (was 52.0). Python Tunis->Sousse now 204.9 min Louage direct (was 232.9 train+taxi).
- Still: Python cheapest walk degeneracy partly capped by 120min rule; Tunis local Python cheapest 112min pure walk (0DT) remains under cap but should be capped by total walk distance instead.

## Remaining problems
- Docker daemon not running: services/routing/Dockerfile + docker-compose transit-routing config-validated, image build not executed
- k8s manifests not applied (no cluster)
- 20 disambiguated stations still need real geocoding (les_salines__bus etc); seed_disambiguated not yet wired into loaders
- Tunis local 112min pure-walk cheapest still compliant under 120min cap (needs distance cap)
