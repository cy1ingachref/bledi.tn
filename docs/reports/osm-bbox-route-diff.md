# OSM bbox vs export route-relation diff

Read-only comparison of two OSM route-relation sources. No data was changed.

- bbox file: `<Downloads>/67.geojson`
- export: `data\osm_overpass\tunisia_pt.json`
- Tunisia box (same as `verify_open_seed.py`): (30.23, 37.56, 7.5, 11.65)

## Counts

- Relations in bbox file: **67**
- Relations in export: **35**
- In both: **35**
- Only in bbox file: **32**
  - centre inside Tunisia box: 29
  - centre outside Tunisia box: 3
- Only in export: **0**

## Counts by route type

- bbox: {'bus': 30, 'ferry': 3, 'light_rail': 14, 'train': 20}
- export: {'bus': 14, 'ferry': 2, 'light_rail': 14, 'train': 5}
- only_in_bbox: {'bus': 16, 'ferry': 1, 'train': 15}
- only_in_bbox_inside_tunisia: {'bus': 15, 'train': 14}

## Ids in both

- 1355997 — تونس - حلق الوادي - المرسى (light_rail)
- 1365361 — خط 1: بن عروس - ساحة برشلونة (light_rail)
- 1366793 — خط 2 - أريانة => ساحة الجمهورية (light_rail)
- 1368272 — خط 3 - ابن خلدون-ساحة برشلونة (light_rail)
- 1368401 — خط 4 - خير الدين-تونس البحرية (light_rail)
- 1368402 — خط 5 - الانطلاقة-ساحة برشلونة (light_rail)
- 1368621 — خط ٦ - المروج ٤-تونس البحرية (light_rail)
- 1420736 — خط تونس-حلق الوادي-المرسى (light_rail)
- 1714964 — Ligne 19E (bus)
- 2014909 — (unnamed) (bus)
- 2014910 — (unnamed) (bus)
- 2327848 — Marseille - تونس (ferry)
- 2718393 — تونس - سوسة - صفاقس - قابس (train)
- 3304108 — (unnamed) (bus)
- 3315935 — 1 البستان (bus)
- 3316457 — 2 حشاد (bus)
- 3316983 — تونس - برج السدرية، الرياض (train)
- 3349176 — تونس 6 : باب الجبلي -> سيدي صالح (bus)
- 5308947 — غار الدماء-تونس (train)
- 7743162 — Bus 52B (bus)
- 8501148 — خط 4 - خير الدين-تونس البحرية (light_rail)
- 8510679 — خط 5 - الانطلاقة-ساحة برشلونة (light_rail)
- 8510787 — خط 3 - ابن خلدون-ساحة برشلونة (light_rail)
- 9525004 — خط 1: ساحة برشلونة - بن عروس (light_rail)
- 9530552 — خط 2 - ساحة الجمهورية => أريانة (light_rail)
- 9530553 — خط 6 - المروج 4-تونس البحرية (light_rail)
- 15654114 — خط E : بوقطفة-سيدي حسين - تونس (train)
- 15654115 — خط E : تونس - بوقطفة-سيدي حسين (train)
- 19283055 — Bus 12 : Jardin Thameur --> Terminus Zayatine (bus)
- 19283575 — Bus 12 : Terminus Zayatine --> Jardin Thameur (bus)
- 19283576 — Bus 12 : Jardin Thameur --> Terminus Zayatine (bus)
- 19284761 — Bus 11 : Tunis Marine --> Jbel Lahmer (bus)
- 19284762 — Bus 11 : Jbal Lahmer --> Tunis Marine (bus)
- 19427704 — أجيم - الجرف (ferry)
- 19679813 — Bus 3710: Marche de Gros -> Borj Cedria (bus)

## Ids only in bbox file

| id | name | name:fr | ref | operator | route | centre lat/lon | in TN box |
|---|---|---|---|---|---|---|---|
| 1714965 | Ligne 19 |  | 19 | TRANSTU | bus | 36.7508854, 10.1216541 | yes |
| 2244366 |  |  |  |  | bus | 33.8753374, 10.09098 | yes |
| 2994206 |  |  |  |  | bus | 36.8804896, 10.3266762 | yes |
| 5288756 | Salerno - Palermo - تونس | Salerne - Palerme - Tunis |  | Grimaldi Lines, Grandi Navi Veloci | ferry | 38.7318319, 12.5245488 | NO |
| 5308946 | بنزرت-تونس | Bizerte-Tunis | الخطوط الكبيرة | الشركة الوطنية للسكك الحديدية التونسية | train | 37.0260373, 9.9324623 | yes |
| 5926679 | 19 ت | 19 C | 19 ت | شركة النقل بتونس | bus | 36.7677177, 10.2141662 | yes |
| 6780746 | عنابة - تبسة | Annaba - Tébessa |  | الشركة الوطنية للنقل بالسكك الحديدية | train | 36.1513575, 7.91244 | yes |
| 6783500 | قسنطينة - عنابة | Constantine - Annaba |  | الشركة الوطنية للنقل بالسكك الحديدية | train | 36.632089, 7.1778436 | NO |
| 7510849 |  |  |  |  | bus | 33.8659389, 10.7939005 | yes |
| 7510852 |  |  |  |  | bus | 33.8749098, 10.8505888 | yes |
| 7510853 |  |  |  |  | bus | 33.8738976, 10.8581451 | yes |
| 7510854 |  |  |  |  | bus | 33.8740362, 10.8581361 | yes |
| 7510855 |  |  |  |  | bus | 33.8761192, 10.8569388 | yes |
| 8676959 | تونس - سوسة - صفاقس - توزر | Tunis - Sousse - Sfax - Tozeur |  | الشركة الوطنية للسكك الحديدية التونسية | train | 35.3606583, 9.4538415 | yes |
| 8676960 | تونس - المهدية | Tunis - Mahdia |  | الشركة الوطنية للسكك الحديدية التونسية | train | 36.1455329, 10.6224232 | yes |
| 8676961 | سوسة باب الجديد - المهدية | Sousse Bab Jedid - Mahdia |  | الشركة الوطنية للسكك الحديدية التونسية | train | 35.6595582, 10.8528851 | yes |
| 8676962 | الكاف - السرس - تونس | Le Kef - Sers - Tunis |  | الشركة الوطنية للسكك الحديدية التونسية | train | 36.4351769, 9.4681206 | yes |
| 8688078 | عنابة ← سيدي عمار | Annaba → Sidi Amar |  | الشركة الوطنية للنقل بالسكك الحديدية | train | 36.8521602, 7.7350421 | yes |
| 16003005 | سيدي عمار ← عنابة | Sidi Amar → Annaba |  | الشركة الوطنية للنقل بالسكك الحديدية | train | 36.8521602, 7.7350421 | yes |
| 16003176 | عنابة - برحال | Annaba - Berrahal |  | الشركة الوطنية للنقل بالسكك الحديدية | train | 36.8604267, 7.6047219 | yes |
| 16006851 | شيحاني ← عنابة | Chihani → Annaba |  | الشركة الوطنية للنقل بالسكك الحديدية | train | 36.7722676, 7.7571911 | yes |
| 16006855 | عنابة ← شيحاني | Annaba → Chihani |  | الشركة الوطنية للنقل بالسكك الحديدية | train | 36.7722676, 7.7571911 | yes |
| 16694211 |  | RFR Ligne D : Tunis - Gobaâ | D |  | train | 36.8026392, 10.1276041 | yes |
| 16694212 |  | RFR Ligne D : Gobaâ - Tunis | D |  | train | 36.802604, 10.1276222 | yes |
| 17889536 | Ligne du Cap Bon |  |  |  | train | 36.4281863, 10.6535827 | yes |
| 18468277 |  |  |  |  | bus | 36.8397685, 7.6739641 | yes |
| 18468278 |  |  |  |  | bus | 36.8406138, 7.6734193 | yes |
| 18468572 |  |  |  |  | bus | 36.8418295, 7.6810202 | yes |
| 18468573 |  |  |  |  | bus | 36.8426748, 7.6804754 | yes |
| 18472594 |  |  |  |  | bus | 36.7962445, 7.4095296 | NO |
| 18559186 |  |  |  |  | bus | 36.8538987, 7.5917603 | yes |
| 18559187 |  |  |  |  | bus | 36.8548484, 7.5912155 | yes |

## Ids only in export


## Interpretation (owner decision)

If **many Tunisian relations appear only in the bbox file**, the area-based query is losing relations and the query should change — that is the owner's decision, not this report's. If the bbox-only relations are **mostly outside Tunisia**, the current export's 35 relation count stands.
