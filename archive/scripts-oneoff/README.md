# Archived one-off scripts

These scripts were one-off repairs and data-inspection helpers written against
the original author's absolute local paths. They are kept for provenance only;
they are not on the runtime path and are not referenced by any CI workflow.

They were moved out of `scripts/` during the M6 portability cleanup so that
kept code can be run from any checkout directory. The `scripts/check_no_local_paths.py`
CI guard excludes this `archive/` tree.
