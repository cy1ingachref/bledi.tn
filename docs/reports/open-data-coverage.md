# Open-data coverage report

Reproducible from `scripts/open_coverage_report.py`; generated from the
legacy seed, the open seed and the fetch manifest. No network access.

## Provenance

- Manifest `fetched_at_utc`: `None`
- OSM base timestamp: `None`
- Export SHA-256: `None`

## Stations

- Legacy: 7,452; open: 2
- Matched (same mode, ≤150 m, normalised name): 0
- Unmatched legacy: 7,452; open-only: 2
- Match rate: 0.0%

By mode (legacy): bus 6987, louage 29, metro 85, rail 24, rural 18, taxi 13, train 220, unknown 76

By governorate (legacy): Ain 1, Ariana 1, Bardo 1, Beni khalled 1, Bizerte 26, Bouargoub 1, Boumhel el bassatine 2, Gaafour 1, Ghardimaou 1, Grombalia 1, Hammamet 1, Haouaria 2, Hey hbib 2, Kairaouen 1, Kalaat al andalous 1, Kef 1, Kelibia 1, Khazanet 1, Korba 2, Mateur 2, Menzel temime 1, Metlaoui 1, Mjez el beb 1, Monastir 1, Nabeul 1, Oued ellil 2, Oueslatia 1, Radès 1, Sakeit zit 3, Sakeyet ezzit 1, Sejnene 1, Sidi amor 1, Sidi thabet 1, Tabarka 1, Tina 2, Tinja 1, Tunis 2, Zaghouan 2, Zaghouen 1, unknown 7377

## Lines

- Legacy: 379; open: 1
- Matched: 0; missing: 379; open-only: 1
- Match rate: 0.0%

### 30 largest missing legacy lines (estimated ridership proxy = stop count)

| Line | Name | Mode | Stops |
|---|---|---|---|
| bus_836_31b | Ligne 31B: Ali Balahouan - Lycée Kalaate Al Andalouss | bus | 63 |
| bus_779_3710 | Ligne 3710: Marché De Gros - Terminus Borj Cedria | bus | 55 |
| bus_773_116 | Ligne 116: Bab Alioua - Steg Tebourba | bus | 50 |
| bus_852_410b | Ligne 410B: Marché De Gros - Boudria  | bus | 50 |
| bus_752_77 | Ligne 77: Terminus Tunis Marine Bus - Terminus 44/44A/77 | bus | 49 |
| bus_833_31a | Ligne 31A: Ali Balahouan - Terminus Bech Hamba | bus | 49 |
| bus_725_37 | Ligne 37: Station De Bus Mornag - Terminus Borj Cedria | bus | 48 |
| bus_860_54a | Ligne 54A: Cebalet Cheikh - Terminus Cité Chaker | bus | 47 |
| bus_828_26a | Ligne 26A: Station Barcelone - Station De Bus Mornag | bus | 46 |
| bus_861_54a | Ligne 54A/: Cité El Elmi (Terminus) - Terminus Cité Chaker | bus | 46 |
| bus_727_42 | Ligne 42: Ali Balahouan - Terminus Tebourba | bus | 45 |
| bus_884_44a | Ligne 44A: Station Barcelone - Terminus 44/44A/77 | bus | 45 |
| train_24_sncft | Ligne SNCFT: Tunis Ville - Sakiet Ezzit | train | 44 |
| bus_719_31 | Ligne 31: Ali Balahouan - Terminus 31 | bus | 44 |
| bus_829_26b | Ligne 26B: Station Barcelone - Station De Bus Mornag | bus | 42 |
| bus_791_16d | Ligne 16D: Ali Balahouan - Terminus Sidi Othman | bus | 41 |
| bus_858_44d | Ligne 44D: Depot Charguia - Mosquée Oued Ellil | bus | 41 |
| bus_715_25 | Ligne 25: Avenue Carthage - Ferch Annabi (Terminus) | bus | 40 |
| bus_729_44 | Ligne 44: Intilaka - Lycée Kalaate Al Andalouss | bus | 40 |
| bus_816_23h | Ligne 23H: Rabattement Slimen Kahia - Sidi Medien | bus | 40 |
| bus_826_25d | Ligne 25D: Avenue Carthage - Cité Salem | bus | 40 |
| bus_825_25b | Ligne 25B: Avenue Carthage - Bir Jeddid 2 | bus | 39 |
| bus_834_31c | Ligne 31C: Ali Balahouan - Chorfech 3 | bus | 39 |
| bus_845_34a | Ligne 34A: Jardin Thameur - Prison Civile Mornagiaa | bus | 39 |
| bus_722_34 | Ligne 34: Jardin Thameur - Epicier Lagraa | bus | 38 |
| bus_814_23e | Ligne 23E: Rabattement Slimen Kahia - Griaat | bus | 38 |
| bus_735_54 | Ligne 54: Mourouj 5 - Terminus Cité Chaker | bus | 37 |
| bus_775_460 | Ligne 460: Les Abattoirs - Boudria  | bus | 37 |
| bus_801_19g | Ligne 19G: Hopital Des Enfants - Lycée Ibn Mandhour | bus | 37 |
| bus_721_33 | Ligne 33: Jardin Thameur - Terminus Mghira | bus | 36 |

## Caveat

If the open seed was built from a synthetic fixture (no real export on
disk), these numbers are NOT a coverage assessment — refetch the export
and regenerate before any cutover decision.
