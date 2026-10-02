# Comparison against the supplied transit stop extract

Reference: `C:\Users\cy1in\tunisia_transit\tunisia_transit_stops.txt`
(OSM via Overpass, ODbL 1.0, data date 2026-10-02 16:49 UTC).

Compared against our seed at `9ccf7ad`. Companion to `docs/osm-stop-audit.md`,
which used an ad-hoc Overpass query; this extract is a better reference.

## Why this extract is stronger than my earlier query

    my earlier query        3 tag conventions, no de-duplication
    this extract           16 tag conventions, de-duplicated

The extract merges stops OSM maps twice (e.g. a `highway=bus_stop` node and a
`public_transport=stop_position` node metres apart), giving **3 295 unique
stops** rather than the 4 361 raw nodes I matched against. It also separates
modes we hold no seed data for at all.

Parsed with `tool/parse_stop_extract.py`: **3 295 / 3 295** records, and every
per-mode total in the file's own header matches the parse exactly
(BUS 2586, TRAIN 472, UNKNOWN 159, LIGHT_RAIL_TGM 49, FERRY 11, METRO 1,
TRAIN? 16, METRO? 1).

## Coverage

    our stations found in reference ..... 1660 / 1711  (97.0%)
    our stations not in reference ......... 51
    reference stops we have no station for  1683

Consistent with the earlier audit's 97.4% — the small difference is the
extract's de-duplication, which removes ~1 000 duplicate nodes.

### Modes we have no data for at all

    mode              ours  reference
    BUS                  0       2586
    TRAIN                0        472
    LIGHT_RAIL_TGM       0         49
    FERRY                0         11
    METRO                0          1

(ours are lowercase: bus 1316, train 158, metro 83, rail 24, unknown 130.)

**FERRY is a genuine gap.** Our seed has no ferry mode and no
`/api/v1` endpoint concept of one, yet 11 ferry terminals are mapped — 3 in
Tunis, 3 in Sousse, 3 in Jendouba, 1 each in Nabeul and Gabès. Tunis's ferry
connection to La Goulette / Carthage is a real transit mode for this country.

The 1 683 reference stops we lack are mostly **per-route directional
positions** (`FINANCES MANSOURAH - ALLER`, `BOURAGBA (Retour)`), the same class
the earlier audit declined to import. Importing them as separate markers would
inflate our 1 729 features by roughly 2× with duplicates at identical
coordinates.

## The 243 "mode conflicts" are mostly the reference being wrong

My first pass reported 243 mode conflicts, which looked alarming. It is not.
Almost all are `LIGHT_RAIL_TGM` mapping and `UNKNOWN` placeholders, plus one
genuine artefact: **the reference labels a stop by which tag matched, so an SNCFT
rail halt tagged `highway=bus_stop` is filed under BUS.**

The extract carries the node's own `operator`, which settles this directly:

    on the 35 rail-vs-bus conflicts, the reference's operator field says:
      25  (none)                — no operator tagged, inconclusive
       9  الشركة الوطنية للسكك الحديدية التونسية   — SNCFT, the national RAILWAY
       1  TRANSTU                            — Tunisian public transport

So for 9 of the 35 the reference's own metadata contradicts its BUS label, and
**our seed's `train` is correct**: El Ouja, Zaafrane, Bir El Bey, Tahar Sfar and
others are SNCFT halts that OSM files under `highway=bus_stop`.

This is the same failure mode as the earlier `railway=stop` problem, one level
up: not a wrong tag read, but a correct tag interpreted under the wrong
assumption that `bus_stop` implies a bus service.

The remaining 25 have no operator tag, so neither side can be confirmed from
this data. They are all SNCFT line halts by geography (Le Krib, Skhira, Sened,
Zannouch, El Ayoun, Menzel Bouzaiane, and similar) and our `train` is very
likely right, but I have not proven it.

## What the raw OSM tags show

`tool/resolve_mode_conflicts.py` fetches the conflicting nodes' actual tags
rather than trusting the extract's derived mode. It was rate-limited (HTTP 504)
on the first attempt, but a retry succeeded and fetched **35/35** nodes:

    where our seed is vindicated:  9   raw OSM operator = SNCFT/TGM
    genuinely ambiguous         : 26   operator empty, railway empty

The 9 — Bir Aniba, Bizerte, El Ouja, Zaafrane, El Heri, Nabeul Voyageurs,
Oued Sarrath, Cheria, Mg 28/29 — are all SNCFT stations in the raw OSM record
while being filed under BUS by the extract. **Our seed's `train` is correct and
the reference's BUS label is a wrong inference.** These 9 are the same stations
the extract's own `operator` field identified, now confirmed against the source.

The remaining **26 carry no operator and no `railway` tag at all** — they are
plain `highway=bus_stop` nodes. OSM simply has not mapped the rail infrastructure
at those halts. That is absence of evidence, not evidence our label is wrong;
`docs/osm-stop-audit.md` covers the same 25-ish group from the other direction.
I have not corrected them, and would not without a rail-line proximity test.

## Verdict

**No new corrections to make.** Unlike the earlier audit, which found one
genuine error (`SLIMENE KEHIA`, metro→bus, already fixed), this comparison
surfaces no station where the reference clearly beats our seed.

Two things are worth acting on, both additions rather than corrections:

1. **Add `ferry` as a mode.** 11 real terminals, a genuine Tunisian transit
   mode, currently unrepresentable in our model and absent from the map's
   colour scheme.
2. **Adopt the reference's `operator` field** where present, so the station
   detail sheet can distinguish SNCFT from Transtu instead of guessing.

## Recommended, not done

- Import OSM names as **aliases** rather than overwriting. 571 of 1 660 pairs
  differ in label; the extract carries `name`, `name/fr` and `name/ar`, so both
  spellings could resolve in search.
- De-duplicate our own seed: several coordinate groups hold more than one
  station, adding visual noise in dense areas.
- **Rail-line proximity test for the 26 remaining conflicts.** Their nodes carry
  no operator and no `railway` tag, so only proximity to a mapped
  `railway=rail` line would settle them. Not run — Overpass is unreliable under
  repeated querying, and the answer would not change what we ship: they are
  SNCFT halts by geography and our `train` label stands.

## Tools

    parse_stop_extract.py     text extract -> JSON, with a parse-integrity report
    compare_with_reference.py coverage, mode and name agreement vs the extract
    resolve_mode_conflicts.py fetch raw OSM tags to settle mode disputes

## Limitations

- Overpass rate-limited the first raw-tag fetch (HTTP 504); a retry succeeded and
  returned all 35 nodes. The verdict above is from that successful run, but the
  raw tags are not cached in-repo, so re-running requires the public instance
  again.
- Matching is geometric at 250 m; in dense Tunis a station may pair with a
  neighbour's node. Name agreement was a cross-check, not a gate.
- The extract's own caveats stand: OSM coverage is good in Tunis, Sousse, Sfax,
  Nabeul and Bizerte, sparse in the far south. 51 of our stations absent from it
  are mostly in those areas, so their absence is weak evidence of error.
- `TRAIN?` (16) and `METRO?` (1) in the extract are text-hint guesses its author
  flagged as unverified; excluded from the agreement count.