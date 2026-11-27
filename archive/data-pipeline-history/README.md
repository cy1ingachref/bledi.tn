# Archived data-pipeline history

Intermediate seed snapshots that are no longer on the runtime path. They are
kept for provenance only; `git mv` preserved their history.

| File | Produced by | Why archived |
|---|---|---|
| `seed_all_tunisia_routes.cleaned.final.json` | `archive/scripts-oneoff/final_integrity_fix.py` | Superseded intermediate; the kept pipeline regenerates `seed_all_tunisia_routes.CLEANED.corrected.json` directly from the tagged seed. |
| `seed_disambiguated.json` | `archive/scripts-oneoff/fix_shared_ids.py` | One-off shared-id disambiguation snapshot; the canonical seed is `seed_all_tunisia_routes.tagged.json`. |

The runtime chain is documented in `data/SOURCES.md`. Neither file is read by
`services/transit`, `services/routing`, or any CI workflow.
