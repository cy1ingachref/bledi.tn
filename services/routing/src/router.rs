//! Dijkstra / A* over (station, line-arrived-on) — mirrors planner.py/router.py.
//! Objectives: fastest (time + transfer penalty), cheapest (fare-weighted),
//! preference (only the requested mode(s), fastest among them).

use crate::graph::{fare_for, haversine_m, wait_for_mode, Graph, Station, MAX_PURE_WALK_SEC, TRANSFER_PENALTY_SEC, WALK_SPEED_MS};
use serde::Serialize;
use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet};

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Objective { Fastest, Cheapest, FewestTransfers }
impl Objective {
    pub fn parse(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "cheapest" | "cheap" => Objective::Cheapest,
            "fewest_transfers" | "fewest" => Objective::FewestTransfers,
            _ => Objective::Fastest,
        }
    }
}

#[derive(Serialize, Clone)]
pub struct Leg { pub from: String, pub to: String, pub line: String, pub mode: String,
    pub distance_m: f64, pub time_s: f64, pub fare: f64 }
#[derive(Serialize)]
pub struct RouteResult { pub found: bool, pub objective: String, pub duration_s: f64,
    pub fare: f64, pub transfers: usize, pub distance_m: f64, pub legs: Vec<Leg>, pub message: Option<String> }

#[derive(Eq, PartialEq)]
struct QItem { cost: u64, station: String, line: String }
impl Ord for QItem {
    fn cmp(&self, other: &Self) -> Ordering { other.cost.cmp(&self.cost).then_with(|| self.station.cmp(&other.station)) }
}
impl PartialOrd for QItem { fn partial_cmp(&self, other: &Self) -> Option<Ordering> { Some(self.cmp(other)) } }

fn edge_cost(obj: Objective, time_s: f64, fare: f64, is_transfer: bool, penalty: f64) -> f64 {
    match obj {
        // cheapest: 1 DT ≈ 3600 s-equivalent so fares dominate but time breaks ties
        Objective::Cheapest => fare * 3600.0 + time_s,
        Objective::FewestTransfers => time_s + if is_transfer { penalty * 30.0 } else { 0.0 },
        Objective::Fastest => time_s + if is_transfer { penalty } else { 0.0 },
    }
}

pub fn route(g: &Graph, from_lat: f64, from_lon: f64, to_lat: f64, to_lon: f64,
             objective: Objective, allowed_modes: Option<&HashSet<String>>) -> RouteResult {
    route_inner(g, from_lat, from_lon, to_lat, to_lon, objective, allowed_modes, true)
}

fn route_inner(g: &Graph, from_lat: f64, from_lon: f64, to_lat: f64, to_lon: f64,
             objective: Objective, allowed_modes: Option<&HashSet<String>>, allow_walk_edges: bool) -> RouteResult {
    let obj_name = match objective { Objective::Fastest => "fastest", Objective::Cheapest => "cheapest", Objective::FewestTransfers => "fewest_transfers" };
    let starts = g.nearest(from_lat, from_lon, 2000.0);
    let ends: HashSet<String> = g.nearest(to_lat, to_lon, 2000.0).into_iter().map(|(id, _)| id).collect();
    if starts.is_empty() || ends.is_empty() {
        return RouteResult { found: false, objective: obj_name.into(), duration_s: 0.0, fare: 0.0,
            transfers: 0, distance_m: 0.0, legs: vec![],
            message: Some("no station within 2 km of origin/destination".into()) };
    }
    // A* heuristic: straight line at fastest possible speed (train 60 km/h)
    let max_v = 60.0 / 3.6;
    let heur = |lat: f64, lon: f64| haversine_m(lat, lon, to_lat, to_lon) / max_v;

    let mut dist: HashMap<(String, String), f64> = HashMap::new();
    let mut prev: HashMap<(String, String), Option<((String, String), crate::graph::Edge)>> = HashMap::new();
    let mut pq = BinaryHeap::new();
    for (id, d) in &starts {
        let st = (id.clone(), String::new());
        let c = d / WALK_SPEED_MS;
        dist.insert(st.clone(), c);
        prev.insert(st.clone(), None);
        pq.push(QItem { cost: (c as u64), station: id.clone(), line: String::new() });
    }
    let mut visited: HashSet<(String, String)> = HashSet::new();
    let mut best_state: Option<(String, String)> = None;
    let mut best_cost = f64::INFINITY;
    while let Some(item) = pq.pop() {
        let state = (item.station.clone(), item.line.clone());
        if visited.contains(&state) { continue; }
        visited.insert(state.clone());
        let cost = *dist.get(&state).unwrap_or(&f64::INFINITY);
        if cost >= best_cost { break; }
        if ends.contains(&item.station) {
            let s = &g.stations[&item.station];
            let end_walk = haversine_m(s.lat, s.lon, to_lat, to_lon) / WALK_SPEED_MS;
            if cost + end_walk < best_cost { best_cost = cost + end_walk; best_state = Some(state.clone()); }
        }
        let Some(edges) = g.adj.get(&item.station) else { continue };
        for e in edges {
            if e.mode == "walk" && !allow_walk_edges { continue; }
            if let Some(allowed) = allowed_modes {
                if e.mode != "walk" && !allowed.contains(&e.mode) { continue; }
            }
            let is_transfer = !e.line.is_empty() && e.line != item.line && !item.line.is_empty();
            let is_boarding = !e.line.is_empty() && e.line != item.line;
            let wait = if is_boarding && e.mode != "walk" { wait_for_mode(&e.mode) } else { 0.0 };
            let c = edge_cost(objective, e.time_s + wait, e.fare, is_transfer || is_boarding, TRANSFER_PENALTY_SEC);
            let ns = (e.to.clone(), e.line.clone());
            let nc = cost + c;
            if nc < *dist.get(&ns).unwrap_or(&f64::INFINITY) {
                dist.insert(ns.clone(), nc);
                prev.insert(ns.clone(), Some((state.clone(), e.clone())));
                let h = g.stations.get(&e.to).map(|s: &Station| heur(s.lat, s.lon)).unwrap_or(0.0);
                pq.push(QItem { cost: (nc + h) as u64, station: e.to.clone(), line: e.line.clone() });
            }
        }
    }
    let Some(best) = best_state else {
        return RouteResult { found: false, objective: obj_name.into(), duration_s: 0.0, fare: 0.0,
            transfers: 0, distance_m: 0.0, legs: vec![], message: Some("no route found".into()) };
    };
    let mut legs = Vec::new();
    let mut cur = best;
    while let Some(Some((p, e))) = prev.get(&cur) {
        legs.push(Leg { from: p.0.clone(), to: e.to.clone(), line: e.line.clone(), mode: e.mode.clone(),
            distance_m: e.dist_m, time_s: e.time_s, fare: e.fare });
        cur = p.clone();
    }
    legs.reverse();
    let mut transfers = 0usize;
    let mut last_line = String::new();
    for l in &legs { if !l.line.is_empty() && l.line != last_line && !last_line.is_empty() { transfers += 1; } if !l.line.is_empty() { last_line = l.line.clone(); } }
    let duration_s: f64 = legs.iter().map(|l| l.time_s).sum();
    // Fare charged once per boarding: group consecutive legs on the same line
    // (walk legs are free), mirroring Python fares.fare_for_itinerary.
    let mut legs = legs;
    let mut fare = 0.0;
    let mut i = 0usize;
    while i < legs.len() {
        if legs[i].line.is_empty() || legs[i].mode == "walk" { legs[i].fare = 0.0; i += 1; continue; }
        let mut j = i;
        let mut grouped_m = 0.0;
        while j < legs.len() && legs[j].line == legs[i].line && legs[j].mode != "walk" {
            grouped_m += legs[j].distance_m; j += 1;
        }
        let group_fare = fare_for(&legs[i].mode, grouped_m);
        // Put the whole boarding charge on the first leg (base) so that
        // sum(leg.fare) == total fare; intermediate legs keep marginal fare.
        let marginal_sum: f64 = legs[i..j].iter().map(|l| l.fare).sum();
        legs[i].fare += group_fare - marginal_sum;
        fare += group_fare;
        i = j;
    }
    fare = (fare * 100.0).round() / 100.0;
    let distance_m: f64 = legs.iter().map(|l| l.distance_m).sum();
    let result = RouteResult { found: true, objective: obj_name.into(), duration_s, fare, transfers, distance_m, legs, message: None };
    // Pure-walk cap: a walk-only itinerary over MAX_PURE_WALK_SEC (120 min) is
    // only returned when no transit route exists (shared_tunables.json).
    if result.legs.iter().all(|l| l.mode == "walk") && duration_s > MAX_PURE_WALK_SEC && allow_walk_edges {
        let transit = route_inner(g, from_lat, from_lon, to_lat, to_lon, objective, allowed_modes, false);
        if transit.found && transit.legs.iter().any(|l| l.mode != "walk") { return transit; }
    }
    result
}
