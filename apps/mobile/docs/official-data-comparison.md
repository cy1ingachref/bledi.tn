# Official operator exports vs our seed

Source: `C:\Users\cy1in\Downloads\transport` — a portal export of per-operator
Tunisian transport datasets, fetched 2026-10-03.

Compared against our seed at `d1f56ab`. This supersedes the two OSM-based
audits (`docs/osm-stop-audit.md`, `docs/stop-extract-comparison.md`) on every
question of *mode*, because it is the operators' own data rather than a
volunteer map.

## What was parsed

`tool/parse_official_data.py` sniffs each file's encoding, delimiter and
column names rather than assuming one schema. 3 195 rows read, **3 171 unique
stops** after de-duplicating operator+mode+coordinates:

    TRANSTU   1687   bus      2804 bus total
    SORETRAS   967
    SNCFT      243   train     367 train + metro total
    SRTM       150
    TGM         80   metro
    RFR         44

    3 128 / 3 171 carry a name

Five export directories were unread (SRTGN, SRTJ, SNTRI ×2, SORETRAS station
list) — their files have no usable coordinate columns. Nothing depends on them.

## Headline

    our stations corroborated by an operator export .... 1689 / 1711  (98.7%)
    our stations with no official stop nearby ............ 22
    official stops we have no station for ................ 1518

    our rail/metro stations ............................. 266
      corroborated as rail/metro by an operator ......... 255  (95.9%)
      operator says bus instead ......................... 8
      no official stop nearby ........................... 3

## The 61 apparent contradictions are not errors

A naive read of "operator says bus, we say rail" flags 62 stations. Every one
resolves on inspection:

**Same place, two modes — real interchanges (38).** Both an official rail stop
and an official bus stop sit within 250 m, and the rail stop is at 0 m:

    Mahdia Ezzahra    rail 0 m (SNCFT)  | bus 167 m (SORETRAS)
    Mannouba          rail 0 m (SNCFT)  | bus  59 m (TRANSTU)
    Jedeida           rail 0 m (SNCFT)  | bus  76 m (TRANSTU)
    Depot Farhat Hached  rail 0 m (SNCFT) | bus 15 m (TRANSTU)

A station served by both a train and a bus is correctly labelled `train`; the
nearby bus stop is a different place that happens to share a name.

**Name collisions across the country (24).** Our rail station and a bus stop
share a name but are 142 km apart (`Les Salines`), or the bus stop is a
different operator's (`Sfax` matches an SRTM bus stop 1.6 km away).

**My own incorrect fix — `SLIMENE KEHIA`.** This is the important one.

## SLIMENE KEHIA: my OSM "fix" was wrong, and I reverted it

In commit `c800f0e` I changed this station from `metro` to `bus`, on the
evidence that OSM tags its node `bus=yes` + `highway=bus_stop` with no
`railway` node nearby. That was the OSM tag trap, at its worst: the node is
mis-tagged and I treated the absence of a railway tag as evidence.

The operator export settles it:

    0 m   TGM      metro   'SLIMANE KAHIA'      ← official, exact position
    73 m  TRANSTU  bus     'RABATTEMENT SLIMEN KAHIA'
    174 m TRANSTU  bus     'SLIMEN KAHIA'

TGM — the metro operator — lists it as a metro station at the same coordinates.
**Reverted to `metro`**, with `mode_source: official-operator-export` and the
`mode_corrected_from` marker removed.

This is the concrete cost of trusting a volunteer map over the operator: I
"fixed" a station into the wrong mode and it would have shipped.

## 217 of our rail stations have an exact official name match

    our rail/metro stations with a matching name in an operator rail export: 217 (81.6%)

    Sousse Bab Jdid     SNCFT/train  0 m      Sousse Sud      SNCFT/train  0 m
    Monastir            SNCFT/train  0 m      La Faculte      SNCFT/train  0 m
    Le Krib             SNCFT/train  0 m      Skhira          SNCFT/train  0 m
    Carthage Byrsa      TGM/metro    0 m      ETTADHAMEN      TGM/metro    0 m

The 26 conflicts the OSM audit could not resolve — Le Krib, Skhira, El Bardo,
Sened, Zannouch and others — are SNCFT halts in the operators' own data. Our
labels were right; OSM simply had not mapped the rail infrastructure there.

## Remaining gaps, in priority order

1. **1 518 official stops we have no station for.** Mostly TRANSTU bus stops
   and SORETRAS regional stops. This is the single largest improvement
   available: our seed carries 1 711 stations, the operators publish 3 171.
   Importing them would roughly double network coverage, including the regions
   our seed covers thinly.
2. **22 of our stations have no official stop within 250 m.** Mostly border and
   rural posts (`Bir Mouzaina`, `Ajim`, `Douane Mateur`, `Camp Militaire
   Deguela`). Some are customs and military posts rather than passenger stops,
   so absence may be correct.
3. **Five exports still unread** — SRTGN, SRTJ, SNTRI, and the SORETRAS station
   list. Their files need a different parse strategy; together they likely hold
   a few hundred more stops.
4. **`mode=unknown` (130 stations) still unclassified.** The exports could
   resolve many: `Haidra`, `Foussana` and `Voie Ballastiere-El hrich` are all
   SNCFT rail stops at 0 m in the official data while our seed calls them
   `unknown`.

## What should change in the seed

Not applied yet, because these are bulk data changes rather than a single
correction, and they need your call:

- **Import the 1 518 missing official stops.** Highest-value change by far.
- **Reclassify the 130 `unknown` stations** from operator mode.
- Keep the existing 1 711; they carry line membership the exports do not.

## Limitations

- Position matching is geometric at 250 m. A station can pair with a
  neighbouring stop of the same name, so name agreement was used as a
  cross-check rather than a gate.
- The 62 "contradictions" are resolved by reasoning about each case, not by an
  automated rule. An importer should encode the rule explicitly: prefer the
  rail reading when an official rail stop is within 250 m.
- `Le Hraïria` and `Bougatfa-Sidi Hassine` have nearest official rail stops at
  886 m and 1.3 km, and two RFR records in the export have an **empty name**.
  Those specific exports may be incomplete; our labels for the two stations are
  plausible but not corroborated.
- File provenance: this is a portal export, not a versioned dataset. Record the
  fetch date (2026-10-03) in any commit that vendors it.