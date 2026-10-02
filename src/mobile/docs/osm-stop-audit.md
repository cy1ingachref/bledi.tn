# OSM stop audit — findings

Comparison of the BLEDI.TN seed against live OpenStreetMap public-transport
data, run 2026-10-02.

## Why OSM, and how

The URL referenced was `wiki.openstreetmap.org/wiki/Tunisia#/map/0/10/36.6640/10.0937`.
The `#map/...` fragment is a **viewport**, not a dataset — the wiki page carries
no stop data. What that map draws comes from OpenStreetMap, so OSM is the
ground truth for "which stops exist, and where".

Method (`tool/compare_with_osm.py` for coverage, `tool/classify_conflicts.py`
for the mode question, sharing `tool/osm_common.py`):

- Overpass query for `public_transport=*`, `highway=bus_stop` and
  `railway=*` across Tunisia → **4 361** transport nodes.
- Matched to seed stations within **250 m** using a lat/lon bucket grid.
- Raw OSM nodes cached in `tool/osm_nodes_cache.json` so re-analysis is free and
  does not re-hit Overpass (which rate-limits with HTTP 504).

## Headline result

    seed stations checked                 1711
    matched to an OSM stop within 250 m   1666  (97.4%)
    no OSM stop within 250 m                45
    name mismatch on confirmed pairs       544  (1122 exact after normalisation)

**Conclusion: positions are substantially correct.** 97.4% of our stations land
on a real, independently-mapped OSM transport node.

## The one real data error found

    SLIMENE KEHIA   36.8033, 10.0991
    our seed: mode = metro
    OSM:       bus=yes, highway=bus_stop, public_transport=stop_position
               (no railway=* tag anywhere within 250 m)

This is the only station that is genuinely mis-classified. Our seed calls it a
**metro** stop; OSM maps it as a **bus** stop and has no rail node near it.

Worth noting this station is served by both a metro line and bus lines in our own
seed data, so the metro assignment is not arbitrary — but the stop as mapped is a
bus stop. Recommend flipping it to `bus` unless a source confirms otherwise.

## Mode conflicts that are NOT errors

The first pass flagged 63 "our seed says rail, OSM says bus" cases. All but the
one above are **tag-vocabulary artefacts**, not data errors:

    tag vocabulary on the conflicting OSM nodes
      public_transport=stop_position   87
      railway=stop                     54
      highway=bus_stop                 35
      bus=yes                          26
      public_transport=platform        18

`railway=stop` and `public_transport=stop_position` are **not bus-exclusive**
tags — Tunisian SNCFT halts and TGM metro platforms carry them. My first
comparison script only recognised `railway=station|halt|tram_stop`, so it scored
correctly-mapped rail stops as bus stops.

After treating those tags as rail-aware, and requiring no rail-tagged node within
250 m, exactly **1** station remains genuinely wrong.

Verified positives:

    CITÉ MUNICIPALE (36.74844,10.18873) — OSM: stop + 3 level_crossing within 66 m
    EL MONTAZAH    (36.74290,10.19319) — OSM: stop + rail switch within 31 m

Both are real metro stops; the surrounding rail infrastructure confirms it.

## Names

544 of 1 666 confirmed pairs differ from the OSM label. These are **our
abbreviations or different transliterations**, not location errors:

    ours Sousse Bab Jdid          | OSM Sousse Bab Djedid          (18 m)
    ours Sousse Zi                | OSM Sousse Zone Industrielle   (20 m)
    ours Aeroport Skanes Monastir | OSM Aéroport Monastir           (43 m)
    ours Ksar Helal Zi            | OSM Ksar Hellal Zone Industrielle (20 m)
    ours Mahdia ZT                | OSM Mahdia Zone Touristique    (6 m)
    ours Moknine Voyageurs        | OSM Moknine                    (11 m)

The seed source strips diacritics and expands "Zi" (zone industrielle). OSM is
more verbose. Where a name is genuinely more standard in OSM (accented forms:
*Aéroport*, *Faculté*, *Baghdadi*, *Sayada*) we would be better adopting the OSM
spelling and keeping the seed name as an alias.

**Recommendation:** do not treat a name difference as a defect. If name quality
matters, the correct move is to *import* `name`, `name:fr`, `name:ar` and
`name:latin` from OSM as aliases rather than overwrite our names, so both
spellings resolve in search.

## OSM stops we do not have

The first pass reported ~2 351 OSM stops with no seed station. Most are **bus-stop
positions for individual route directions**, not distinct places:

    CITE GHALLAMA (Retour)          36.7491,10.0249
    20 MARS L23C/D (Retour)        36.7490,10.0056
    BOURAGBA (Aller)                36.7372,10.0391

OSM models a stop per (route, direction). Our seed models a stop per *place*.
Importing all 2 351 would multiply our markers ~1.4× with directional duplicates
at identical or near-identical coordinates, which is worse for the map than the
current behaviour.

## Recommended corrections, in priority order

1. **Fix `SLIMENE KEHIA`**: `mode` metro → bus. One line, one station.
2. **Add OSM name aliases** rather than replacing names, so accented and
   standard spellings resolve in search.
3. **Consider de-duplicating** our own seed: 27 coordinate groups contain more
   than one station (e.g. `terminus_tunis_marine_bus` and `sntri_7225` at
   36.80038,10.19039). Collapsing to one marker per coordinate would cut
   visual noise in dense areas.
4. **Do not import** the ~2 351 directional OSM stops as separate markers.

## Limitations

- OSM coverage in Tunisia is uneven: dense around Tunis, sparse in the south. A
  missing OSM stop is weak evidence that our station is wrong.
- Matching is purely geometric (250 m). In dense areas a station may pair with a
  neighbour's node; name agreement was used as a cross-check, not a gate.
- Overpass rate-limited repeated queries (HTTP 504). Findings here come from the
  single cached country-wide fetch; re-runs should use
  `tool/osm_nodes_cache.json` rather than re-querying.
- `SLIMENE KEHIA` is reported as an error because no rail node is within 250 m
  *and* OSM explicitly tags it as a bus stop. It should be confirmed against a
  second source before being flipped, since it is served by a metro line in our
  own data.