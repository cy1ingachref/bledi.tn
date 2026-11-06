//! Stop graph: stations, lines, grid index, bidirectional edges.
//!
//! Data sources (first that exists wins, relative to the data dir):
//!   1. `transport_map_corrected.json` ({metadata, by_mode:{mode:{stations,lines}}})
//!   2. `seed_all_tunisia_routes.CLEANED.corrected.json` ({stations, lines})
//! `data/tables/index.json` (379 lines) is the table catalogue; the lines above
//! already carry the per-line station arrays, so tables/ is not needed to build
//! edges (Phase 3A snapped tables, if present later, can replace source 1).
//! Speeds/fares mirror services/transit/.../domain/{tunables,fares}.py.

use serde::Deserialize;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

pub const SPEED_KMH: &[(&str, f64)] = &[
    ("train", 60.0), ("rail", 55.0), ("metro", 30.0), ("bus", 22.0),
    ("rfr", 22.0), ("tram", 22.0), ("rural", 22.0), ("louage", 100.0),
    ("louaj", 100.0), ("taxi", 45.0), ("walk", 4.5), ("unknown", 22.0),
];
pub const FARE: &[(&str, f64, f64)] = &[ // (mode, base DT, DT/km) — fares.py
    ("bus", 0.5, 0.0), ("tram", 0.5, 0.0), ("metro", 0.6, 0.0),
    ("train", 4.0, 0.09), ("rail", 4.0, 0.09), ("louage", 1.0, 0.15),
    ("louaj", 1.0, 0.15), ("taxi", 0.6, 0.52), ("walk", 0.0, 0.0),
];
pub const FARE_CAP_DT: &[(&str, f64)] = &[ // per-boarding caps — shared_tunables.json
    ("train", 15.0), ("rail", 15.0), ("louage", 20.0), ("louaj", 20.0),
];
pub const WAIT_S_BY_MODE: &[(&str, f64)] = &[ // per-mode boarding wait (s) — tunables.py DEFAULT_WAIT_BY_MODE
    ("train", 600.0), ("rail", 600.0), ("metro", 300.0), ("bus", 600.0),
    ("rfr", 600.0), ("tram", 600.0), ("rural", 600.0), ("louage", 600.0),
    ("louaj", 600.0), ("taxi", 0.0), ("walk", 0.0), ("unknown", 600.0),
];
pub const TRANSFER_PENALTY_SEC: f64 = 180.0;
pub const FEWEST_TRANSFERS_PENALTY_SEC: f64 = 5400.0;
pub const WALK_SPEED_MS: f64 = 4.5 / 3.6;
const CELL_DEG: f64 = 0.01; // ~1.1 km grid cell
const MAX_WALK_EDGE_M: f64 = 900.0;
pub const MAX_DIRECT_WALK_M: f64 = 1000.0;
pub const MAX_PURE_WALK_SEC: f64 = 7200.0; // 120 min — shared_tunables.json max_pure_walk_min

pub fn wait_for_mode(mode: &str) -> f64 {
    WAIT_S_BY_MODE.iter().find(|(m, _)| *m == mode).map(|(_, v)| *v).unwrap_or(600.0)
}
pub fn fare_cap_for(mode: &str) -> Option<f64> {
    FARE_CAP_DT.iter().find(|(m, _)| *m == mode).map(|(_, v)| *v)
}

pub fn speed_kmh(mode: &str) -> f64 {
    SPEED_KMH.iter().find(|(m, _)| *m == mode).map(|(_, v)| *v).unwrap_or(22.0)
}
pub fn fare_for(mode: &str, dist_m: f64) -> f64 {
    // Charged ONCE per boarding of a line (see router.rs fare grouping).
    let (b, pk) = FARE.iter().find(|(m, _, _)| *m == mode).map(|(_, b, p)| (*b, *p)).unwrap_or((0.5, 0.0));
    let mut f = (b + pk * dist_m / 1000.0).round() * 100.0 / 100.0;
    if let Some(cap) = fare_cap_for(mode) { f = f.min(cap); }
    f
}
pub fn marginal_fare(mode: &str, dist_m: f64) -> f64 {
    // Per-edge fare for Dijkstra: distance part only. The base is charged once
    // per boarding in router.rs grouping, not per stop-pair edge — charging
    // the base per edge produced 69 DT Tunis->Sousse.
    let (_, pk) = FARE.iter().find(|(m, _, _)| *m == mode).map(|(_, b, p)| (*b, *p)).unwrap_or((0.5, 0.0));
    pk * dist_m / 1000.0
}
pub fn haversine_m(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    const R: f64 = 6_371_000.0;
    let (p1, p2) = (lat1.to_radians(), lat2.to_radians());
    let dp = (lat2 - lat1).to_radians();
    let dl = (lon2 - lon1).to_radians();
    let a = (dp / 2.0).sin().powi(2) + p1.cos() * p2.cos() * (dl / 2.0).sin().powi(2);
    2.0 * R * a.sqrt().asin()
}

#[derive(Debug, Clone)]
pub struct Station { pub id: String, pub name: String, pub lat: f64, pub lon: f64, pub mode: String }

#[derive(Debug, Clone)]
pub struct Line { pub id: String, pub number: String, pub name: String, pub mode: String, pub stations: Vec<String> }

#[derive(Debug, Clone)]
pub struct Edge { pub to: String, pub line: String, pub mode: String, pub dist_m: f64, pub time_s: f64, pub fare: f64 }

pub struct Graph {
    pub stations: HashMap<String, Station>,
    pub lines: Vec<Line>,
    pub mode_of_line: HashMap<String, String>,
    pub adj: HashMap<String, Vec<Edge>>,
    grid: HashMap<(i32, i32), Vec<String>>,
    pub source: String,
}

#[derive(Deserialize)]
struct MapFile { by_mode: Option<HashMap<String, ModeBlock>>, stations: Option<Vec<RawStation>>, lines: Option<Vec<RawLine>> }
#[derive(Deserialize)]
struct ModeBlock { stations: Option<Vec<RawStation>>, lines: Option<Vec<RawLine>> }
#[derive(Deserialize, Clone)]
struct RawStation { id: String, name: Option<String>, lat: Option<f64>, lon: Option<f64>, mode: Option<String> }
#[derive(Deserialize, Clone)]
struct RawLine { id: String, number: Option<String>, name: Option<String>, mode: Option<String>, stations: Option<Vec<String>> }

fn cell(lat: f64, lon: f64) -> (i32, i32) { ((lat / CELL_DEG).floor() as i32, (lon / CELL_DEG).floor() as i32) }

impl Graph {
    fn build(stations: HashMap<String, Station>, lines: Vec<Line>, source: String) -> Self {
        let mut mode_of_line = HashMap::new();
        let mut adj: HashMap<String, Vec<Edge>> = HashMap::new();
        let mut grid: HashMap<(i32, i32), Vec<String>> = HashMap::new();
        for s in stations.values() { grid.entry(cell(s.lat, s.lon)).or_default().push(s.id.clone()); }
        for ln in &lines {
            mode_of_line.insert(ln.id.clone(), ln.mode.clone());
            let v = speed_kmh(&ln.mode) / 3.6;
            for pair in ln.stations.windows(2) {
                let (Some(a), Some(b)) = (stations.get(&pair[0]), stations.get(&pair[1])) else { continue };
                let d = haversine_m(a.lat, a.lon, b.lat, b.lon);
                let e1 = Edge { to: b.id.clone(), line: ln.id.clone(), mode: ln.mode.clone(), dist_m: d, time_s: d / v, fare: marginal_fare(&ln.mode, d) };
                let e2 = Edge { to: a.id.clone(), line: ln.id.clone(), mode: ln.mode.clone(), dist_m: d, time_s: d / v, fare: marginal_fare(&ln.mode, d) };
                adj.entry(a.id.clone()).or_default().push(e1);
                adj.entry(b.id.clone()).or_default().push(e2);
            }
        }
        // Walk edges between stations in same/neighbour cells within 900 m (capped per station).
        let ids: Vec<String> = stations.keys().cloned().collect();
        for id in &ids {
            let s = &stations[id];
            let (cx, cy) = cell(s.lat, s.lon);
            let mut added = 0;
            'outer: for dx in -1..=1 { for dy in -1..=1 {
                for other in grid.get(&(cx + dx, cy + dy)).cloned().unwrap_or_default() {
                    if other == *id || added >= 8 { continue; }
                    let o = &stations[&other];
                    let d = haversine_m(s.lat, s.lon, o.lat, o.lon);
                    if d > 1.0 && d <= MAX_WALK_EDGE_M {
                        adj.entry(id.clone()).or_default().push(Edge {
                            to: other.clone(), line: String::new(), mode: "walk".into(),
                            dist_m: d, time_s: d / WALK_SPEED_MS, fare: 0.0,
                        });
                        added += 1;
                        if added >= 8 { break 'outer; }
                    }
                }
            }}
        }
        Graph { stations, lines, mode_of_line, adj, grid, source }
    }

    /// Nearest stations to (lat,lon) within radius, via grid expansion.
    pub fn nearest(&self, lat: f64, lon: f64, radius_m: f64) -> Vec<(String, f64)> {
        let mut out = Vec::new();
        let (cx, cy) = cell(lat, lon);
        let span = ((radius_m / 1000.0) / (CELL_DEG * 111.0)).ceil() as i32 + 1;
        for dx in -span..=span { for dy in -span..=span {
            for id in self.grid.get(&(cx + dx, cy + dy)).cloned().unwrap_or_default() {
                let s = &self.stations[&id];
                let d = haversine_m(lat, lon, s.lat, s.lon);
                if d <= radius_m { out.push((id, d)); }
            }
        }}
        out.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
        out
    }

    pub async fn load(data_dir: &Path) -> Result<Graph, String> {
        for name in ["transport_map_corrected.json", "seed_all_tunisia_routes.CLEANED.corrected.json"] {
            let p: PathBuf = data_dir.join(name);
            if !p.exists() { continue; }
            let text = crate::io::read_to_string(&p).await.map_err(|e| format!("read {}: {e}", p.display()))?;
            let parsed: MapFile = serde_json::from_str(&text).map_err(|e| format!("parse {}: {e}", p.display()))?;
            let mut stations = HashMap::new();
            let mut lines: Vec<Line> = Vec::new();
            let mut seen_lines = std::collections::HashSet::new();
            let mut ingest = |raw_st: Vec<RawStation>, raw_ln: Vec<RawLine>, stations: &mut HashMap<String, Station>, lines: &mut Vec<Line>| {
                for s in raw_st {
                    if let (Some(lat), Some(lon)) = (s.lat, s.lon) {
                        stations.entry(s.id.clone()).or_insert(Station {
                            name: s.name.clone().unwrap_or_else(|| s.id.clone()),
                            mode: s.mode.clone().unwrap_or_else(|| "bus".into()),
                            id: s.id, lat, lon,
                        });
                    }
                }
                for l in raw_ln {
                    if seen_lines.insert(l.id.clone()) {
                        lines.push(Line { id: l.id, number: l.number.unwrap_or_default(), name: l.name.unwrap_or_default(),
                            mode: l.mode.unwrap_or_else(|| "bus".into()), stations: l.stations.unwrap_or_default() });
                    }
                }
            };
            if let Some(by_mode) = parsed.by_mode {
                for (_, block) in by_mode { ingest(block.stations.unwrap_or_default(), block.lines.unwrap_or_default(), &mut stations, &mut lines); }
            } else {
                ingest(parsed.stations.unwrap_or_default(), parsed.lines.unwrap_or_default(), &mut stations, &mut lines);
            }
            if stations.is_empty() { return Err(format!("no stations parsed from {}", p.display())); }
            return Ok(Graph::build(stations, lines, name.to_string()));
        }
        Err(format!("no data file in {} (looked for transport_map_corrected.json)", data_dir.display()))
    }
}
