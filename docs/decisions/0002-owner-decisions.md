# 0002 — Owner decisions (2026-11-26)

The owner resolved the open gates in `bledi-agent-brief.md`. These decisions
are binding for the work on branch `feat/brief-reconciliation`.

1. **Data licensing — rebuild from open sources.** The Tunismapper-derived
   seed is not to be relied on for redistribution. Build the transit dataset
   from open sources (OSM public-transport relations / operator data) instead
   of seeking permission or making the data private. Until the rebuild is
   complete, the existing derived files remain in place for the running app;
   no new feature may add a dependency on unverifiable third-party data.
   T1.5/T1.6 are resolved in favour of an open-source rebuild + an explicit
   code license, with dataset provenance documented separately.

2. **Repo hygiene — remove the zip.** `bledi.tn-review.zip` / any archived
   handoff zip is not kept in the repo (currently no `*.zip` is tracked;
   T1.1 is already satisfied). Publish handoffs as GitHub Releases instead.

3. **Frontend — keep React.** `apps/web-react` (React + Vite + Tailwind 4)
   is the only supported frontend. The SvelteKit `apps/web` remains only as
   a legacy reference until it is retired; no new work goes into it. The
   brief's `apps/web` paths are to be read as `apps/web-react`.

4. **API method — Rust-first, most efficient.** Prefer Rust/axum services
   for routing and new endpoints; keep FastAPI only where it is the existing
   tested reference (`services/transit`). Gateway contract and OpenAPI stay
   authoritative. For the tracking service (phase 5) choose Rust + axum +
   Redis + Postgres/PostGIS unless a measured benchmark shows otherwise.

5. **Live database — later.** Do not spend this phase wiring a live/shared
   database into development or CI workflows. CI continues to skip tests
   that require a live DB. The Docker stack's local db is for local runtime
   only; no service may depend on it for routing.

6. **Brief — update to reality.** Reconcile the brief's §1/§2–§8 paths with
   the actual monorepo rather than restructuring the working repo to match
   the stale document. This decision supersedes the "target repo layout" in
   §2 as a description of the present layout; it remains a target only where
   explicitly staged in §8.

7. **Process — fix CI, then ship.** After the above: fix CI until green,
   commit on this branch, push it, wait for GitHub CI green, then merge the
   PR into `origin/main`. Commit/push only on this explicit instruction.
   Git identity for all commits: `Achref Ferjani <cy1ingachref@gmail.com>`.

Owner did not choose (remain open, do not guess): pilot region scope (T1.7),
exact raw-ping retention window and minimum-contributor rule for tracking
(§4). These must be settled before those tasks land.
