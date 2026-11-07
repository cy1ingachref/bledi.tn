//! Bledi routing service — axum 0.7.
//! Endpoints: GET /health, GET /route?from=&to=&objective=, POST /route, GET /lines
//! `from`/`to` accept a station id, "lat,lon", or use from_lat/from_lon/to_lat/to_lon.

mod graph;
mod io;
mod router;

use axum::{extract::{Query, State}, http::StatusCode, routing::get, Json, Router};
use graph::Graph;
use router::{route, Objective, RouteResult};
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, sync::Arc};

#[derive(Clone)]
struct AppState { g: Arc<Graph> }

#[derive(Serialize)]
struct Health { status: &'static str, stations: usize, lines: usize, edges: usize, io_backend: &'static str, data_source: String }

async fn health(State(s): State<AppState>) -> Json<Health> {
    Json(Health { status: "ok", stations: s.g.stations.len(), lines: s.g.lines.len(),
        edges: s.g.adj.values().map(|v| v.len()).sum(), io_backend: io::backend_name(), data_source: s.g.source.clone() })
}

#[derive(Deserialize)]
struct RouteParams { from: Option<String>, to: Option<String>, objective: Option<String>,
    from_lat: Option<f64>, from_lon: Option<f64>, to_lat: Option<f64>, to_lon: Option<f64>,
    mode: Option<String>, modes: Option<String> }

#[derive(Deserialize)]
struct RouteBody { from: Option<String>, to: Option<String>, objective: Option<String>,
    from_lat: Option<f64>, from_lon: Option<f64>, to_lat: Option<f64>, to_lon: Option<f64>,
    mode: Option<String>, modes: Option<String>, allowed_modes: Option<Vec<String>> }

fn resolve_endpoint(g: &Graph, id: Option<&str>, lat: Option<f64>, lon: Option<f64>)
    -> Result<(f64, f64), (StatusCode, String)> {
    if let (Some(lat), Some(lon)) = (lat, lon) { return Ok((lat, lon)); }
    let Some(v) = id else { return Err((StatusCode::BAD_REQUEST, "missing from/to (station id, \"lat,lon\", or *_lat/*_lon)".into())) };
    if let Some((la, lo)) = v.split_once(',') {
        if let (Ok(la), Ok(lo)) = (la.trim().parse(), lo.trim().parse()) { return Ok((la, lo)); }
    }
    g.stations.get(v).map(|s| (s.lat, s.lon))
        .ok_or_else(|| (StatusCode::NOT_FOUND, format!("unknown station: {v}")))
}

fn do_route(g: &Graph, p: &RouteParams) -> Result<Json<RouteResult>, (StatusCode, String)> {
    let (flat, flon) = resolve_endpoint(g, p.from.as_deref(), p.from_lat, p.from_lon)?;
    let (tlat, tlon) = resolve_endpoint(g, p.to.as_deref(), p.to_lat, p.to_lon)?;
    let obj = Objective::parse(p.objective.as_deref().unwrap_or("fastest"));
    let mut allowed: Option<HashSet<String>> = None;
    let mut modes: Vec<String> = Vec::new();
    if let Some(m) = &p.mode { modes.push(m.clone()); }
    if let Some(m) = &p.modes { modes.extend(m.split(',').map(|s| s.trim().to_string())); }
    if !modes.is_empty() { allowed = Some(modes.into_iter().collect()); }
    Ok(Json(route(g, flat, flon, tlat, tlon, obj, allowed.as_ref())))
}

async fn get_route(State(s): State<AppState>, Query(p): Query<RouteParams>)
    -> Result<Json<RouteResult>, (StatusCode, String)> { do_route(&s.g, &p) }

async fn post_route(State(s): State<AppState>, Json(b): Json<RouteBody>)
    -> Result<Json<RouteResult>, (StatusCode, String)> {
    let mut allowed = b.allowed_modes.clone();
    let p = RouteParams { from: b.from, to: b.to, objective: b.objective, from_lat: b.from_lat,
        from_lon: b.from_lon, to_lat: b.to_lat, to_lon: b.to_lon, mode: b.mode, modes: b.modes };
    let r = do_route(&s.g, &p)?;
    if let Some(modes) = allowed.take() {
        let set: HashSet<String> = modes.into_iter().collect();
        let (flat, flon) = resolve_endpoint(&s.g, p.from.as_deref(), p.from_lat, p.from_lon)?;
        let (tlat, tlon) = resolve_endpoint(&s.g, p.to.as_deref(), p.to_lat, p.to_lon)?;
        return Ok(Json(route(&s.g, flat, flon, tlat, tlon, Objective::parse(p.objective.as_deref().unwrap_or("fastest")), Some(&set))));
    }
    Ok(r)
}

#[derive(Serialize)]
struct LineInfo { id: String, number: String, name: String, mode: String, stations: usize }
async fn lines(State(s): State<AppState>) -> Json<Vec<LineInfo>> {
    Json(s.g.lines.iter().map(|l| LineInfo { id: l.id.clone(), number: l.number.clone(),
        name: l.name.clone(), mode: l.mode.clone(), stations: l.stations.len() }).collect())
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt().with_env_filter(tracing_subscriber::EnvFilter::from_default_env()).init();
    let data_dir = std::env::var("BLEDI_DATA_DIR").map(std::path::PathBuf::from).unwrap_or_else(|_| {
        // services/routing -> ../../data ; also handles running from repo root
        ["../../data", "../data", "data", "../../../data"].iter().map(std::path::PathBuf::from)
            .find(|p| p.join("transport_map_corrected.json").exists()).unwrap_or_else(|| std::path::PathBuf::from("../../data"))
    });
    let g = match Graph::load(&data_dir).await {
        Ok(g) => { tracing::info!("loaded {} stations, {} lines from {}", g.stations.len(), g.lines.len(), g.source); g }
        Err(e) => { tracing::error!("failed to load graph from {}: {e}", data_dir.display()); std::process::exit(1); }
    };
    let app = Router::new()
        .route("/health", get(health))
        .route("/route", get(get_route).post(post_route))
        .route("/lines", get(lines))
        .layer(tower_http::cors::CorsLayer::permissive())
        .with_state(AppState { g: Arc::new(g) });
    let port: u16 = std::env::var("PORT").ok().and_then(|v| v.parse().ok()).unwrap_or(8081);
    let listener = tokio::net::TcpListener::bind(("0.0.0.0", port)).await.expect("bind");
    tracing::info!("routing listening on :{port} (io: {})", io::backend_name());
    axum::serve(listener, app).await.expect("serve");
}
