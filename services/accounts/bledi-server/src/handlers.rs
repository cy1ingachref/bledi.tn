use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::Json;
use bledi_core::*;
use serde_json::{json, Value};
use std::sync::OnceLock;
use uuid::Uuid;

use crate::auth::{AuthError, AuthUser};
use crate::ratelimit::Decision;
use crate::state::AppState;
use crate::validate;

// ── Health ──────────────────────────────────────────────────────────────────

pub async fn health() -> Json<Value> {
    Json(json!({ "status": "ok", "service": "bledi-server", "version": "0.1.0" }))
}

// ── Error helpers ───────────────────────────────────────────────────────────

/// A 400 with a client-safe message. Used for every validation failure so the
/// caller learns which field is wrong.
fn bad_request(msg: impl Into<String>) -> (StatusCode, Json<Value>) {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({ "error": msg.into() })),
    )
}

/// A 500 that does NOT echo the database error to the client.
///
/// The raw `sqlx::Error` frequently contains the failing SQL, the table and
/// column names, and occasionally the bound values. That is a free schema dump
/// for an attacker and no help to a legitimate client, so it is logged
/// server-side and replaced with a generic message.
fn err(e: sqlx::Error) -> (StatusCode, Json<Value>) {
    tracing::error!("database error: {e}");
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({ "error": "Internal server error" })),
    )
}

fn conflict(msg: impl Into<String>) -> (StatusCode, Json<Value>) {
    (StatusCode::CONFLICT, Json(json!({ "error": msg.into() })))
}

fn not_found(msg: impl Into<String>) -> (StatusCode, Json<Value>) {
    (StatusCode::NOT_FOUND, Json(json!({ "error": msg.into() })))
}

fn forbidden(msg: impl Into<String>) -> (StatusCode, Json<Value>) {
    (StatusCode::FORBIDDEN, Json(json!({ "error": msg.into() })))
}

fn internal(msg: impl Into<String>) -> (StatusCode, Json<Value>) {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({ "error": msg.into() })),
    )
}

/// A 429 with a `Retry-After` header.
fn too_many_requests(retry_after_secs: u64) -> (StatusCode, Json<Value>) {
    (
        StatusCode::TOO_MANY_REQUESTS,
        Json(json!({
            "error": "Too many requests",
            "retry_after_secs": retry_after_secs,
        })),
    )
}

/// The client's IP address, for IP-keyed rate limits.
///
/// Prefers the socket peer address from `ConnectInfo`. Only falls back to
/// `X-Forwarded-For` when `TRUST_PROXY_HEADERS` is set, because that header is
/// **client-controlled**: trusting it unconditionally lets any caller pick its
/// own rate-limit bucket by sending a different value on each request, which
/// defeats the limiter entirely. Set `TRUST_PROXY_HEADERS=1` only when the
/// server sits behind a reverse proxy that overwrites the header.
///
/// Falls back to `None` (a single shared bucket) when neither is available,
/// which fails closed: a shared bucket is stricter than a per-IP one, not looser.
fn client_ip(headers: &axum::http::HeaderMap, peer: Option<std::net::SocketAddr>) -> String {
    let trust_proxy = std::env::var("TRUST_PROXY_HEADERS")
        .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
        .unwrap_or(false);

    if trust_proxy {
        if let Some(fwd) = headers.get("x-forwarded-for").and_then(|v| v.to_str().ok()) {
            if let Some(first) = fwd.split(',').next() {
                let first = first.trim();
                if !first.is_empty() {
                    return first.to_string();
                }
            }
        }
    }

    match peer {
        Some(addr) => addr.ip().to_string(),
        None => "unknown".to_string(),
    }
}

/// Postgres SQLSTATE for a unique-constraint violation.
const SQLSTATE_UNIQUE_VIOLATION: &str = "23505";

/// True when a `sqlx::Error` is a unique-constraint violation.
///
/// Matching on the SQLSTATE code is the correct way to detect this. The previous
/// implementation searched the error's `Display` output for the substring
/// "duplicate key", which is fragile: it depends on the driver's message text,
/// which is not part of any contract and changes between versions.
fn is_unique_violation(e: &sqlx::Error) -> bool {
    matches!(
        e,
        sqlx::Error::Database(db) if db.code().as_deref() == Some(SQLSTATE_UNIQUE_VIOLATION)
    )
}

fn hash_password(pw: &str) -> Result<String, AuthError> {
    bcrypt::hash(pw, bcrypt::DEFAULT_COST).map_err(|e| AuthError(e.to_string()))
}

fn verify_password(pw: &str, hash: &str) -> Result<bool, AuthError> {
    bcrypt::verify(pw, hash).map_err(|e| AuthError(e.to_string()))
}

/// A bcrypt hash to verify against when the email is unknown.
///
/// Login must spend the same time whether or not the account exists. Returning
/// early for an unknown email makes "no such user" measurably faster than "wrong
/// password", which is a user-enumeration oracle. Verifying against this dummy
/// hash equalises the two paths.
///
/// Generated lazily on first use rather than pasted as a constant, so there is
/// no magic hash string in the source that could silently become invalid.
fn dummy_password_hash() -> &'static str {
    static DUMMY: OnceLock<String> = OnceLock::new();
    DUMMY.get_or_init(|| {
        bcrypt::hash("timing-equalisation-placeholder", bcrypt::DEFAULT_COST).unwrap_or_else(|_| {
            "$2b$12$0000000000000000000000000000000000000000000000000000".to_string()
        })
    })
}

// ── Auth handlers ───────────────────────────────────────────────────────────

pub async fn register(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
    connect_info: Option<axum::extract::ConnectInfo<std::net::SocketAddr>>,
    Json(req): Json<RegisterRequest>,
) -> Result<(StatusCode, Json<AuthResponse>), (StatusCode, Json<Value>)> {
    let ip = client_ip(&headers, connect_info.map(|c| c.0));
    if let Decision::Deny { retry_after_secs } = state
        .rate_limiter
        .check(&format!("register:{ip}"), state.rate_limits.register)
    {
        return Err(too_many_requests(retry_after_secs));
    }

    let email = validate::email(&req.email).map_err(|e| bad_request(e.0))?;
    validate::password(&req.password).map_err(|e| bad_request(e.0))?;
    let display_name =
        validate::display_name(req.display_name.as_deref()).map_err(|e| bad_request(e.0))?;

    let hash = hash_password(&req.password).map_err(|e| internal(e.0))?;
    let user = sqlx::query_as::<_, User>(
        r#"INSERT INTO users (email, password_hash, display_name)
           VALUES ($1, $2, $3)
           RETURNING id, email, password_hash, display_name, created_at"#,
    )
    .bind(&email)
    .bind(&hash)
    .bind(&display_name)
    .fetch_one(&state.pool)
    .await
    .map_err(|e| {
        if is_unique_violation(&e) {
            conflict("Email already registered")
        } else {
            err(e)
        }
    })?;

    let token = crate::auth::generate_token(&user, &state.jwt_secret).map_err(|e| internal(e.0))?;
    Ok((
        StatusCode::CREATED,
        Json(AuthResponse {
            token,
            user: user.into(),
        }),
    ))
}

pub async fn login(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
    connect_info: Option<axum::extract::ConnectInfo<std::net::SocketAddr>>,
    Json(req): Json<LoginRequest>,
) -> Result<Json<AuthResponse>, (StatusCode, Json<Value>)> {
    // Rate limited BEFORE any password work, so the limiter also caps the CPU
    // cost of bcrypt against a flood of login attempts.
    let ip = client_ip(&headers, connect_info.map(|c| c.0));
    if let Decision::Deny { retry_after_secs } = state
        .rate_limiter
        .check(&format!("login:{ip}"), state.rate_limits.login)
    {
        return Err(too_many_requests(retry_after_secs));
    }

    // Validate shape only. A malformed email cannot match any account, and
    // saying so would be an enumeration oracle — so a bad email takes the same
    // generic-credentials path as an unknown one.
    let email_ok = validate::email(&req.email);

    let user = match &email_ok {
        Ok(email) => sqlx::query_as::<_, User>(
            "SELECT id, email, password_hash, display_name, created_at FROM users WHERE email = $1",
        )
        .bind(email)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?,
        Err(_) => None,
    };

    // Constant-ish time: always run bcrypt, even when there is no such user.
    let invalid_credentials = || {
        (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "error": "Invalid credentials" })),
        )
    };

    let Some(user) = user else {
        let _ = verify_password(&req.password, dummy_password_hash());
        return Err(invalid_credentials());
    };

    if !verify_password(&req.password, &user.password_hash).map_err(|e| internal(e.0))? {
        return Err(invalid_credentials());
    }

    let token = crate::auth::generate_token(&user, &state.jwt_secret).map_err(|e| internal(e.0))?;
    Ok(Json(AuthResponse {
        token,
        user: user.into(),
    }))
}

pub async fn get_me(
    State(state): State<AppState>,
    auth: AuthUser,
) -> Result<Json<PublicUser>, (StatusCode, Json<Value>)> {
    let user = sqlx::query_as::<_, User>(
        "SELECT id, email, password_hash, display_name, created_at FROM users WHERE id = $1",
    )
    .bind(auth.user_id)
    .fetch_optional(&state.pool)
    .await
    .map_err(err)?
    .ok_or_else(|| not_found("User not found"))?;

    Ok(Json(user.into()))
}

// ── Station handlers ────────────────────────────────────────────────────────

#[derive(Debug, serde::Deserialize)]
pub struct StationNearQuery {
    pub lat: f64,
    pub lon: f64,
    pub radius_m: Option<f64>,
}

fn station_from_row(row: sqlx::postgres::PgRow) -> Result<Station, sqlx::Error> {
    use sqlx::Row;
    let modes: Vec<String> = row.try_get("modes").unwrap_or_default();
    let modes: Vec<TransportMode> = modes
        .iter()
        .filter_map(|m| TransportMode::parse(m.as_str()))
        .collect();
    Ok(Station {
        id: row.try_get("id")?,
        name: row.try_get("name")?,
        lat: row.try_get("lat")?,
        lon: row.try_get("lon")?,
        modes,
        city: row.try_get("city")?,
    })
}

pub async fn list_stations(
    State(state): State<AppState>,
) -> Result<Json<Vec<Station>>, (StatusCode, Json<Value>)> {
    let rows = sqlx::query("SELECT id, name, lat, lon, modes, city FROM stations")
        .fetch_all(&state.pool)
        .await
        .map_err(err)?;

    let mut stations = Vec::new();
    for row in rows {
        stations.push(station_from_row(row).map_err(err)?);
    }
    Ok(Json(stations))
}

pub async fn nearby_stations(
    State(state): State<AppState>,
    Query(query): Query<StationNearQuery>,
) -> Result<Json<Vec<Station>>, (StatusCode, Json<Value>)> {
    let (lat, lon) = validate::lat_lon(query.lat, query.lon).map_err(|e| bad_request(e.0))?;
    let radius =
        validate::search_radius_m(query.radius_m, validate::STATION_RADIUS_MAX_M, "radius_m")
            .map_err(|e| bad_request(e.0))?;

    let rows = sqlx::query(
        r#"SELECT id, name, lat, lon, modes, city
           FROM stations
           WHERE earth_box(ll_to_earth($1, $2), $3) @> ll_to_earth(lat, lon)
             AND earth_distance(ll_to_earth(lat, lon), ll_to_earth($1, $2)) <= $3
           ORDER BY earth_distance(ll_to_earth(lat, lon), ll_to_earth($1, $2))
           LIMIT 100"#,
    )
    .bind(lat)
    .bind(lon)
    .bind(radius)
    .fetch_all(&state.pool)
    .await
    .map_err(err)?;

    let mut stations = Vec::new();
    for row in rows {
        stations.push(station_from_row(row).map_err(err)?);
    }
    Ok(Json(stations))
}

pub async fn get_station(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Station>, (StatusCode, Json<Value>)> {
    let row = sqlx::query("SELECT id, name, lat, lon, modes, city FROM stations WHERE id = $1")
        .bind(&id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| not_found("Station not found"))?;

    Ok(Json(station_from_row(row).map_err(err)?))
}

// ── Line handlers ───────────────────────────────────────────────────────────

fn line_from_row(row: sqlx::postgres::PgRow) -> Result<Line, sqlx::Error> {
    use sqlx::Row;
    let station_ids: Vec<String> = row.try_get("station_ids").unwrap_or_default();
    let mode: String = row.try_get("mode")?;
    Ok(Line {
        id: row.try_get("id")?,
        number: row.try_get("number")?,
        name: row.try_get("name")?,
        mode: TransportMode::parse(&mode).unwrap_or(TransportMode::Bus),
        operator: row.try_get("operator")?,
        color: row.try_get("color")?,
        station_ids,
    })
}

pub async fn list_lines(
    State(state): State<AppState>,
) -> Result<Json<Vec<Line>>, (StatusCode, Json<Value>)> {
    let rows =
        sqlx::query("SELECT id, number, name, mode, operator, color, station_ids FROM lines")
            .fetch_all(&state.pool)
            .await
            .map_err(err)?;

    let mut lines = Vec::new();
    for row in rows {
        lines.push(line_from_row(row).map_err(err)?);
    }
    Ok(Json(lines))
}

pub async fn get_line(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Line>, (StatusCode, Json<Value>)> {
    let row = sqlx::query(
        "SELECT id, number, name, mode, operator, color, station_ids FROM lines WHERE id = $1",
    )
    .bind(&id)
    .fetch_optional(&state.pool)
    .await
    .map_err(err)?
    .ok_or_else(|| not_found("Line not found"))?;

    Ok(Json(line_from_row(row).map_err(err)?))
}

// ── Memory helpers ──────────────────────────────────────────────────────────

fn memory_from_row(row: sqlx::postgres::PgRow) -> Result<Memory, sqlx::Error> {
    use sqlx::Row;
    Ok(Memory {
        id: row.try_get("id")?,
        user_id: row.try_get("user_id")?,
        lat: row.try_get("lat")?,
        lon: row.try_get("lon")?,
        title: row.try_get("title")?,
        description: row.try_get("description")?,
        media_url: row.try_get("media_url")?,
        media_type: row.try_get("media_type")?,
        visibility: row.try_get("visibility")?,
        unlock_radius_m: row.try_get("unlock_radius_m")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

/// The full representation, INCLUDING `media_url`.
///
/// Only for the owner's own list, or for a caller that has passed the unlock
/// radius check. Never for a discovery endpoint.
fn memory_to_json(m: &Memory) -> Value {
    json!({
        "id": m.id,
        "user_id": m.user_id,
        "lat": m.lat,
        "lon": m.lon,
        "title": m.title,
        "description": m.description,
        "media_url": m.media_url,
        "media_type": m.media_type.as_str(),
        "visibility": m.visibility.as_str(),
        "unlock_radius_m": m.unlock_radius_m,
        "locked": false,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    })
}

/// The discovery representation: everything EXCEPT `media_url`.
///
/// `GET /memories/nearby` used to return `media_url` for every memory inside the
/// requested radius, which meant anyone could enumerate media URLs across the
/// country with one wide query — and, because `radius_m` was uncapped, the
/// radius could be as wide as they liked. The media is now reachable only
/// through `POST /memories/:id/unlock`, which checks a claimed position against
/// `unlock_radius_m`.
///
/// `locked: true` is explicit so a client can distinguish "this memory has no
/// media yet" from "the media is being withheld from you".
fn memory_to_json_redacted(m: &Memory) -> Value {
    json!({
        "id": m.id,
        "user_id": m.user_id,
        "lat": m.lat,
        "lon": m.lon,
        "title": m.title,
        "description": m.description,
        "media_type": m.media_type.as_str(),
        "visibility": m.visibility.as_str(),
        "unlock_radius_m": m.unlock_radius_m,
        "locked": true,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    })
}

/// True when `viewer` and `owner` have an ACCEPTED friendship, in either
/// direction. `viewer == owner` is always true (you are your own friend for
/// visibility purposes).
async fn are_friends(pool: &sqlx::PgPool, viewer: Uuid, owner: Uuid) -> Result<bool, sqlx::Error> {
    if viewer == owner {
        return Ok(true);
    }
    let row: Option<(i32,)> = sqlx::query_as(
        r#"SELECT 1 FROM friendships
           WHERE status = 'accepted'
             AND ((user_id = $1 AND friend_id = $2) OR (user_id = $2 AND friend_id = $1))
           LIMIT 1"#,
    )
    .bind(viewer)
    .bind(owner)
    .fetch_optional(pool)
    .await?;
    Ok(row.is_some())
}

/// Whether `viewer` may see a memory at all, ignoring the unlock radius.
///
/// - `public`  → any authenticated user
/// - `friends` → the owner, or an accepted friend
/// - `private` → the owner only
async fn may_view(pool: &sqlx::PgPool, viewer: Uuid, memory: &Memory) -> Result<bool, sqlx::Error> {
    if memory.user_id == viewer {
        return Ok(true);
    }
    match memory.visibility {
        Visibility::Public => Ok(true),
        Visibility::Friends => are_friends(pool, viewer, memory.user_id).await,
        Visibility::Private => Ok(false),
    }
}

// ── Memory handlers ─────────────────────────────────────────────────────────

pub async fn list_memories(
    State(state): State<AppState>,
    auth: AuthUser,
) -> Result<Json<Vec<Value>>, (StatusCode, Json<Value>)> {
    // The caller's OWN memories, so the full object (with media_url) is correct.
    let rows = sqlx::query("SELECT * FROM memories WHERE user_id = $1 ORDER BY created_at DESC")
        .bind(auth.user_id)
        .fetch_all(&state.pool)
        .await
        .map_err(err)?;

    let mut memories = Vec::new();
    for row in rows {
        memories.push(memory_to_json(&memory_from_row(row).map_err(err)?));
    }
    Ok(Json(memories))
}

pub async fn nearby_memories(
    State(state): State<AppState>,
    auth: AuthUser,
    Query(query): Query<NearbyMemoriesQuery>,
) -> Result<Json<Vec<Value>>, (StatusCode, Json<Value>)> {
    let (lat, lon) = validate::lat_lon(query.lat, query.lon).map_err(|e| bad_request(e.0))?;
    // Capped, and above the cap is a 400 rather than a silent clamp: a clamped
    // search returns a different answer than the caller asked for.
    let radius =
        validate::search_radius_m(query.radius_m, validate::NEARBY_RADIUS_MAX_M, "radius_m")
            .map_err(|e| bad_request(e.0))?;

    let rows = sqlx::query(
        r#"SELECT * FROM memories
           WHERE (visibility = 'public'
                  OR (visibility = 'friends' AND user_id IN (
                      SELECT friend_id FROM friendships WHERE user_id = $4 AND status = 'accepted'
                      UNION SELECT user_id FROM friendships WHERE friend_id = $4 AND status = 'accepted'
                  ))
                  OR user_id = $4)
             AND earth_box(ll_to_earth($1, $2), $3) @> ll_to_earth(lat, lon)
             AND earth_distance(ll_to_earth(lat, lon), ll_to_earth($1, $2)) <= $3
           ORDER BY earth_distance(ll_to_earth(lat, lon), ll_to_earth($1, $2))
           LIMIT 200"#,
    )
    .bind(lat)
    .bind(lon)
    .bind(radius)
    .bind(auth.user_id)
    .fetch_all(&state.pool)
    .await
    .map_err(err)?;

    let mut memories = Vec::new();
    for row in rows {
        // Redacted: discovery never reveals media.
        memories.push(memory_to_json_redacted(&memory_from_row(row).map_err(err)?));
    }
    Ok(Json(memories))
}

pub async fn create_memory(
    State(state): State<AppState>,
    auth: AuthUser,
    Json(req): Json<CreateMemoryRequest>,
) -> Result<(StatusCode, Json<Value>), (StatusCode, Json<Value>)> {
    let (lat, lon) = validate::lat_lon(req.lat, req.lon).map_err(|e| bad_request(e.0))?;
    let unlock_radius_m =
        validate::unlock_radius_m(req.unlock_radius_m).map_err(|e| bad_request(e.0))?;
    let title = validate::title(req.title.as_deref()).map_err(|e| bad_request(e.0))?;
    let description =
        validate::description(req.description.as_deref()).map_err(|e| bad_request(e.0))?;
    let media_url = validate::media_url(&req.media_url).map_err(|e| bad_request(e.0))?;

    let vis_str = match req.visibility {
        Visibility::Public => "public",
        Visibility::Friends => "friends",
        Visibility::Private => "private",
    };
    let row = sqlx::query(
        r#"INSERT INTO memories (user_id, lat, lon, title, description, media_url, media_type, visibility, unlock_radius_m)
           VALUES ($1, $2, $3, $4, $5, $6, $7::media_type, $8::visibility, $9) RETURNING *"#,
    )
    .bind(auth.user_id)
    .bind(lat)
    .bind(lon)
    .bind(title)
    .bind(description)
    .bind(media_url)
    .bind(req.media_type.as_str())
    .bind(vis_str)
    .bind(unlock_radius_m)
    .fetch_one(&state.pool)
    .await
    .map_err(err)?;

    let memory = memory_from_row(row).map_err(err)?;
    Ok((StatusCode::CREATED, Json(memory_to_json(&memory))))
}

pub async fn get_memory(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(id): Path<Uuid>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    let row = sqlx::query("SELECT * FROM memories WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| not_found("Memory not found"))?;

    let memory = memory_from_row(row).map_err(err)?;

    // Enforce all three visibility levels.
    //
    // Previously only `private` was checked, so ANY authenticated user could
    // read a `friends` memory by UUID, which made the friends level decorative.
    //
    // The denial is 403 rather than 404. That does reveal that an id exists, but
    // ids are random UUIDs and the alternative — 404 for both "missing" and
    // "not yours" — would need the same query anyway. Consistency matters more
    // here than hiding existence, and the response body is the same generic
    // string either way.
    if !may_view(&state.pool, auth.user_id, &memory)
        .await
        .map_err(err)?
    {
        return Err(forbidden("Access denied"));
    }

    Ok(Json(memory_to_json(&memory)))
}

pub async fn update_memory(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(id): Path<Uuid>,
    Json(req): Json<UpdateMemoryRequest>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    let existing = sqlx::query("SELECT user_id FROM memories WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| not_found("Memory not found"))?;

    use sqlx::Row;
    let owner_id: Uuid = existing.try_get("user_id").map_err(err)?;
    if owner_id != auth.user_id {
        return Err(forbidden("Access denied"));
    }

    // Validate only the fields that are actually being changed.
    let title = validate::title(req.title.as_deref()).map_err(|e| bad_request(e.0))?;
    let description =
        validate::description(req.description.as_deref()).map_err(|e| bad_request(e.0))?;
    let unlock_radius_m = match req.unlock_radius_m {
        Some(v) => Some(validate::unlock_radius_m(v).map_err(|e| bad_request(e.0))?),
        None => None,
    };

    let row = sqlx::query("SELECT * FROM memories WHERE id = $1")
        .bind(id)
        .fetch_one(&state.pool)
        .await
        .map_err(err)?;
    let current = memory_from_row(row).map_err(err)?;

    let title = title.or(current.title);
    let description = description.or(current.description);
    let visibility = req.visibility.unwrap_or(current.visibility);
    let unlock_radius_m = unlock_radius_m.unwrap_or(current.unlock_radius_m);

    let row = sqlx::query(
        r#"UPDATE memories SET title=$1, description=$2, visibility=$3, unlock_radius_m=$4, updated_at=now()
           WHERE id=$5 RETURNING *"#,
    )
    .bind(title)
    .bind(description)
    .bind(visibility.as_str())
    .bind(unlock_radius_m)
    .bind(id)
    .fetch_one(&state.pool)
    .await
    .map_err(err)?;

    let updated = memory_from_row(row).map_err(err)?;
    Ok(Json(memory_to_json(&updated)))
}

pub async fn delete_memory(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, (StatusCode, Json<Value>)> {
    let result = sqlx::query("DELETE FROM memories WHERE id = $1 AND user_id = $2")
        .bind(id)
        .bind(auth.user_id)
        .execute(&state.pool)
        .await
        .map_err(err)?;

    if result.rows_affected() == 0 {
        return Err(not_found("Memory not found"));
    }
    Ok(StatusCode::NO_CONTENT)
}

/// Check a claimed position against a memory's `unlock_radius_m`.
///
/// Returns `Ok(distance_m)` when inside the radius, `Err(distance_m)` when
/// outside. Split out from the handler so the decision can be unit-tested
/// without a database.
pub fn within_unlock_radius(
    claimed_lat: f64,
    claimed_lon: f64,
    memory: &Memory,
) -> Result<f64, f64> {
    let distance = haversine_m(claimed_lat, claimed_lon, memory.lat, memory.lon);
    if distance <= memory.unlock_radius_m {
        Ok(distance)
    } else {
        Err(distance)
    }
}

/// `POST /api/v1/memories/:id/unlock`
///
/// The ONLY way to obtain a memory's `media_url`. The caller states where it is;
/// if that claimed position is inside `unlock_radius_m`, the media is returned.
///
/// # What this does and does not prove
///
/// The position is CLIENT-CLAIMED. GPS can be spoofed, so this proves nothing
/// about physical presence. It is a product affordance: it stops casual
/// long-range enumeration of media and makes `unlock_radius_m` mean something.
/// It is not a security boundary, and it must not be described as
/// cryptographic proof of presence.
pub async fn unlock_memory(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(id): Path<Uuid>,
    Json(req): Json<UnlockRequest>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    // Keyed by user, not by IP: unlocking is a per-user resource, and IPs are
    // shared behind NAT.
    let limit_key = format!("unlock:{}", auth.user_id);
    if let Decision::Deny { retry_after_secs } = state
        .rate_limiter
        .check(&limit_key, state.rate_limits.unlock)
    {
        return Err(too_many_requests(retry_after_secs));
    }

    let (lat, lon) = validate::lat_lon(req.lat, req.lon).map_err(|e| bad_request(e.0))?;

    let row = sqlx::query("SELECT * FROM memories WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| not_found("Memory not found"))?;
    let memory = memory_from_row(row).map_err(err)?;

    // Visibility first: a memory the caller may not see is denied regardless of
    // where they claim to be.
    if !may_view(&state.pool, auth.user_id, &memory)
        .await
        .map_err(err)?
    {
        return Err(forbidden("Access denied"));
    }

    match within_unlock_radius(lat, lon, &memory) {
        Ok(distance) => {
            let mut body = memory_to_json(&memory);
            if let Some(obj) = body.as_object_mut() {
                obj.insert("distance_m".to_string(), json!(distance.round()));
                obj.insert("locked".to_string(), json!(false));
            }
            Ok(Json(body))
        }
        Err(distance) => Err((
            StatusCode::FORBIDDEN,
            Json(json!({
                "error": "Too far from this memory",
                "distance_m": distance.round(),
                "unlock_radius_m": memory.unlock_radius_m,
            })),
        )),
    }
}

// ── Friendship handlers ─────────────────────────────────────────────────────

fn friend_view_from_row(row: sqlx::postgres::PgRow) -> Result<FriendView, sqlx::Error> {
    use sqlx::Row;
    Ok(FriendView {
        user_id: row.try_get("user_id")?,
        email: row.try_get("email")?,
        display_name: row.try_get("display_name")?,
        status: row.try_get("status")?,
    })
}

pub async fn list_friendships(
    State(state): State<AppState>,
    auth: AuthUser,
) -> Result<Json<Vec<FriendView>>, (StatusCode, Json<Value>)> {
    let rows = sqlx::query(
        r#"SELECT u.id AS user_id, u.email, u.display_name, f.status
           FROM friendships f
           JOIN users u
             ON u.id = CASE WHEN f.user_id = $1 THEN f.friend_id ELSE f.user_id END
           WHERE f.user_id = $1 OR f.friend_id = $1
           ORDER BY u.email"#,
    )
    .bind(auth.user_id)
    .fetch_all(&state.pool)
    .await
    .map_err(err)?;

    let mut out = Vec::new();
    for row in rows {
        out.push(friend_view_from_row(row).map_err(err)?);
    }
    Ok(Json(out))
}

pub async fn list_friend_requests(
    State(state): State<AppState>,
    auth: AuthUser,
) -> Result<Json<Vec<FriendView>>, (StatusCode, Json<Value>)> {
    let rows = sqlx::query(
        r#"SELECT u.id AS user_id, u.email, u.display_name, f.status
           FROM friendships f
           JOIN users u ON u.id = f.user_id
           WHERE f.friend_id = $1 AND f.status = 'pending'
           ORDER BY f.created_at DESC"#,
    )
    .bind(auth.user_id)
    .fetch_all(&state.pool)
    .await
    .map_err(err)?;

    let mut out = Vec::new();
    for row in rows {
        out.push(friend_view_from_row(row).map_err(err)?);
    }
    Ok(Json(out))
}

/// Look up a user id by email. Used only by the friendship handlers.
async fn user_id_by_email(pool: &sqlx::PgPool, email: &str) -> Result<Option<Uuid>, sqlx::Error> {
    use sqlx::Row;
    let row = sqlx::query("SELECT id FROM users WHERE email = $1")
        .bind(email)
        .fetch_optional(pool)
        .await?;
    match row {
        Some(r) => Ok(Some(r.try_get("id")?)),
        None => Ok(None),
    }
}

pub async fn request_friendship(
    State(state): State<AppState>,
    auth: AuthUser,
    Json(req): Json<FriendEmailRequest>,
) -> Result<(StatusCode, Json<Value>), (StatusCode, Json<Value>)> {
    let email = validate::email(&req.friend_email).map_err(|e| bad_request(e.0))?;

    let target = user_id_by_email(&state.pool, &email)
        .await
        .map_err(err)?
        .ok_or_else(|| not_found("User not found"))?;

    if target == auth.user_id {
        return Err(bad_request("You cannot send a friend request to yourself"));
    }

    // Already accepted, in either direction?
    let accepted: Option<(String,)> = sqlx::query_as(
        r#"SELECT status FROM friendships
           WHERE status = 'accepted'
             AND ((user_id = $1 AND friend_id = $2) OR (user_id = $2 AND friend_id = $1))
           LIMIT 1"#,
    )
    .bind(auth.user_id)
    .bind(target)
    .fetch_optional(&state.pool)
    .await
    .map_err(err)?;
    if accepted.is_some() {
        return Err(conflict("Already friends"));
    }

    // A request the caller already sent.
    let ours: Option<(String,)> = sqlx::query_as(
        "SELECT status FROM friendships WHERE user_id = $1 AND friend_id = $2 LIMIT 1",
    )
    .bind(auth.user_id)
    .bind(target)
    .fetch_optional(&state.pool)
    .await
    .map_err(err)?;
    if ours.is_some() {
        return Err(conflict("Friend request already pending"));
    }

    // A request THEY sent us: treat this as an acceptance, so two people who
    // both tap "add" end up friends instead of deadlocked on two pending rows.
    let theirs: Option<(String,)> = sqlx::query_as(
        "SELECT status FROM friendships WHERE user_id = $1 AND friend_id = $2 LIMIT 1",
    )
    .bind(target)
    .bind(auth.user_id)
    .fetch_optional(&state.pool)
    .await
    .map_err(err)?;
    if theirs.is_some() {
        sqlx::query(
            "UPDATE friendships SET status = 'accepted' WHERE user_id = $1 AND friend_id = $2",
        )
        .bind(target)
        .bind(auth.user_id)
        .execute(&state.pool)
        .await
        .map_err(err)?;
        return Ok((
            StatusCode::OK,
            Json(json!({ "status": "accepted", "user_id": target, "email": email })),
        ));
    }

    sqlx::query("INSERT INTO friendships (user_id, friend_id, status) VALUES ($1, $2, 'pending')")
        .bind(auth.user_id)
        .bind(target)
        .execute(&state.pool)
        .await
        .map_err(|e| {
            if is_unique_violation(&e) {
                conflict("Friend request already pending")
            } else {
                err(e)
            }
        })?;

    Ok((
        StatusCode::CREATED,
        Json(json!({ "status": "pending", "user_id": target, "email": email })),
    ))
}

pub async fn accept_friendship(
    State(state): State<AppState>,
    auth: AuthUser,
    Json(req): Json<FriendEmailRequest>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    let email = validate::email(&req.friend_email).map_err(|e| bad_request(e.0))?;

    let requester = user_id_by_email(&state.pool, &email)
        .await
        .map_err(err)?
        .ok_or_else(|| not_found("User not found"))?;

    // Only the RECIPIENT may accept: the row must be (requester -> caller).
    let result = sqlx::query(
        r#"UPDATE friendships SET status = 'accepted'
           WHERE user_id = $1 AND friend_id = $2 AND status = 'pending'"#,
    )
    .bind(requester)
    .bind(auth.user_id)
    .execute(&state.pool)
    .await
    .map_err(err)?;

    if result.rows_affected() == 0 {
        return Err(not_found("No pending request"));
    }

    Ok(Json(json!({
        "status": "accepted",
        "user_id": requester,
        "email": email,
    })))
}

pub async fn delete_friendship(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(user_id): Path<Uuid>,
) -> Result<StatusCode, (StatusCode, Json<Value>)> {
    // Removes the link in either direction, which covers unfriending an accepted
    // friendship and declining a pending request.
    let result = sqlx::query(
        r#"DELETE FROM friendships
           WHERE (user_id = $1 AND friend_id = $2) OR (user_id = $2 AND friend_id = $1)"#,
    )
    .bind(auth.user_id)
    .bind(user_id)
    .execute(&state.pool)
    .await
    .map_err(err)?;

    if result.rows_affected() == 0 {
        return Err(not_found("Friendship not found"));
    }
    Ok(StatusCode::NO_CONTENT)
}

// ── Favorite handlers ───────────────────────────────────────────────────────

fn favorite_from_row(row: sqlx::postgres::PgRow) -> Result<Favorite, sqlx::Error> {
    use sqlx::Row;
    Ok(Favorite {
        id: row.try_get("id")?,
        user_id: row.try_get("user_id")?,
        kind: row.try_get("kind")?,
        ref_id: row.try_get("ref_id")?,
        label: row.try_get("label")?,
        created_at: row.try_get("created_at")?,
    })
}

fn favorite_to_json(f: &Favorite) -> Value {
    json!({
        "id": f.id,
        "user_id": f.user_id,
        "kind": f.kind.as_str(),
        "ref_id": f.ref_id,
        "label": f.label,
        "created_at": f.created_at,
    })
}

pub async fn list_favorites(
    State(state): State<AppState>,
    auth: AuthUser,
) -> Result<Json<Vec<Value>>, (StatusCode, Json<Value>)> {
    let rows = sqlx::query("SELECT * FROM favorites WHERE user_id = $1 ORDER BY created_at DESC")
        .bind(auth.user_id)
        .fetch_all(&state.pool)
        .await
        .map_err(err)?;

    let mut favorites = Vec::new();
    for row in rows {
        favorites.push(favorite_to_json(&favorite_from_row(row).map_err(err)?));
    }
    Ok(Json(favorites))
}

pub async fn create_favorite(
    State(state): State<AppState>,
    auth: AuthUser,
    Json(req): Json<CreateFavoriteRequest>,
) -> Result<(StatusCode, Json<Value>), (StatusCode, Json<Value>)> {
    let ref_id = validate::ref_id(&req.ref_id).map_err(|e| bad_request(e.0))?;
    let label = validate::label(req.label.as_deref()).map_err(|e| bad_request(e.0))?;

    let kind_str = req.kind.as_str();
    let row = sqlx::query(
        r#"INSERT INTO favorites (user_id, kind, ref_id, label)
           VALUES ($1, $2::favorite_kind, $3, $4)
           ON CONFLICT (user_id, kind, ref_id) DO UPDATE SET label = EXCLUDED.label
           RETURNING *"#,
    )
    .bind(auth.user_id)
    .bind(kind_str)
    .bind(&ref_id)
    .bind(&label)
    .fetch_one(&state.pool)
    .await
    .map_err(err)?;

    let fav = favorite_from_row(row).map_err(err)?;
    Ok((StatusCode::CREATED, Json(favorite_to_json(&fav))))
}

pub async fn delete_favorite(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, (StatusCode, Json<Value>)> {
    let result = sqlx::query("DELETE FROM favorites WHERE id = $1 AND user_id = $2")
        .bind(id)
        .bind(auth.user_id)
        .execute(&state.pool)
        .await
        .map_err(err)?;

    if result.rows_affected() == 0 {
        return Err(not_found("Favorite not found"));
    }
    Ok(StatusCode::NO_CONTENT)
}

// ── Location share handlers ─────────────────────────────────────────────────

fn share_from_row(row: sqlx::postgres::PgRow) -> Result<LocationShare, sqlx::Error> {
    use sqlx::Row;
    Ok(LocationShare {
        id: row.try_get("id")?,
        user_id: row.try_get("user_id")?,
        lat: row.try_get("lat")?,
        lon: row.try_get("lon")?,
        accuracy_m: row.try_get("accuracy_m")?,
        note: row.try_get("note")?,
        is_active: row.try_get("is_active")?,
        expires_at: row.try_get("expires_at")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn share_to_json(s: &LocationShare) -> Value {
    json!({
        "id": s.id,
        "user_id": s.user_id,
        "lat": s.lat,
        "lon": s.lon,
        "accuracy_m": s.accuracy_m,
        "note": s.note,
        "is_active": s.is_active,
        "expires_at": s.expires_at,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    })
}

pub async fn list_location_shares(
    State(state): State<AppState>,
    auth: AuthUser,
) -> Result<Json<Vec<Value>>, (StatusCode, Json<Value>)> {
    let rows =
        sqlx::query("SELECT * FROM location_shares WHERE user_id = $1 ORDER BY updated_at DESC")
            .bind(auth.user_id)
            .fetch_all(&state.pool)
            .await
            .map_err(err)?;

    let mut shares = Vec::new();
    for row in rows {
        shares.push(share_to_json(&share_from_row(row).map_err(err)?));
    }
    Ok(Json(shares))
}

pub async fn nearby_location_shares(
    State(state): State<AppState>,
    auth: AuthUser,
    Query(query): Query<NearbySharesQuery>,
) -> Result<Json<Vec<Value>>, (StatusCode, Json<Value>)> {
    let (lat, lon) = validate::lat_lon(query.lat, query.lon).map_err(|e| bad_request(e.0))?;
    let radius =
        validate::search_radius_m(query.radius_m, validate::NEARBY_RADIUS_MAX_M, "radius_m")
            .map_err(|e| bad_request(e.0))?;

    let rows = sqlx::query(
        r#"SELECT * FROM location_shares
           WHERE is_active = true
             AND (expires_at IS NULL OR expires_at > now())
             AND user_id != $4
             AND user_id IN (
                 SELECT friend_id FROM friendships WHERE user_id = $4 AND status = 'accepted'
                 UNION SELECT user_id FROM friendships WHERE friend_id = $4 AND status = 'accepted'
             )
             AND earth_box(ll_to_earth($1, $2), $3) @> ll_to_earth(lat, lon)
             AND earth_distance(ll_to_earth(lat, lon), ll_to_earth($1, $2)) <= $3
           ORDER BY earth_distance(ll_to_earth(lat, lon), ll_to_earth($1, $2))
           LIMIT 100"#,
    )
    .bind(lat)
    .bind(lon)
    .bind(radius)
    .bind(auth.user_id)
    .fetch_all(&state.pool)
    .await
    .map_err(err)?;

    let mut shares = Vec::new();
    for row in rows {
        shares.push(share_to_json(&share_from_row(row).map_err(err)?));
    }
    Ok(Json(shares))
}

pub async fn create_location_share(
    State(state): State<AppState>,
    auth: AuthUser,
    Json(req): Json<UpdateLocationShareRequest>,
) -> Result<(StatusCode, Json<Value>), (StatusCode, Json<Value>)> {
    let (lat, lon) = validate::lat_lon(req.lat, req.lon).map_err(|e| bad_request(e.0))?;
    let accuracy_m = validate::accuracy_m(req.accuracy_m).map_err(|e| bad_request(e.0))?;
    let note = validate::note(req.note.as_deref()).map_err(|e| bad_request(e.0))?;
    // The README promises shares expire. `expires_at` is therefore required, in
    // the future, and within a bounded horizon — an indefinite share is a
    // privacy leak the user does not expect.
    let expires_at = validate::share_expiry(req.expires_at).map_err(|e| bad_request(e.0))?;

    let row = sqlx::query(
        r#"INSERT INTO location_shares (user_id, lat, lon, accuracy_m, note, is_active, expires_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *"#,
    )
    .bind(auth.user_id)
    .bind(lat)
    .bind(lon)
    .bind(accuracy_m)
    .bind(note)
    .bind(req.is_active)
    .bind(expires_at)
    .fetch_one(&state.pool)
    .await
    .map_err(err)?;

    let share = share_from_row(row).map_err(err)?;
    Ok((StatusCode::CREATED, Json(share_to_json(&share))))
}

pub async fn update_location_share(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(id): Path<Uuid>,
    Json(req): Json<UpdateLocationShareRequest>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    let existing = sqlx::query("SELECT user_id FROM location_shares WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| not_found("Location share not found"))?;

    use sqlx::Row;
    let owner_id: Uuid = existing.try_get("user_id").map_err(err)?;
    if owner_id != auth.user_id {
        return Err(forbidden("Access denied"));
    }

    let (lat, lon) = validate::lat_lon(req.lat, req.lon).map_err(|e| bad_request(e.0))?;
    let accuracy_m = validate::accuracy_m(req.accuracy_m).map_err(|e| bad_request(e.0))?;
    let note = validate::note(req.note.as_deref()).map_err(|e| bad_request(e.0))?;
    let expires_at = validate::share_expiry(req.expires_at).map_err(|e| bad_request(e.0))?;

    let row = sqlx::query(
        r#"UPDATE location_shares
           SET lat=$1, lon=$2, accuracy_m=$3, note=$4, is_active=$5, expires_at=$6, updated_at=now()
           WHERE id=$7 RETURNING *"#,
    )
    .bind(lat)
    .bind(lon)
    .bind(accuracy_m)
    .bind(note)
    .bind(req.is_active)
    .bind(expires_at)
    .bind(id)
    .fetch_one(&state.pool)
    .await
    .map_err(err)?;

    let share = share_from_row(row).map_err(err)?;
    Ok(Json(share_to_json(&share)))
}

pub async fn delete_location_share(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, (StatusCode, Json<Value>)> {
    let result = sqlx::query("DELETE FROM location_shares WHERE id = $1 AND user_id = $2")
        .bind(id)
        .bind(auth.user_id)
        .execute(&state.pool)
        .await
        .map_err(err)?;

    if result.rows_affected() == 0 {
        return Err(not_found("Location share not found"));
    }
    Ok(StatusCode::NO_CONTENT)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ratelimit::RateLimiter;
    use chrono::Utc;

    fn memory_at(lat: f64, lon: f64, radius: f64) -> Memory {
        Memory {
            id: Uuid::new_v4(),
            user_id: Uuid::new_v4(),
            lat,
            lon,
            title: None,
            description: None,
            media_url: "https://media.bledi.tn/x.jpg".to_string(),
            media_type: MediaType::Image,
            visibility: Visibility::Public,
            unlock_radius_m: radius,
            created_at: Utc::now(),
            updated_at: Utc::now(),
        }
    }

    #[test]
    fn inside_the_radius_is_allowed() {
        // ~55 m north of the pin, radius 200 m.
        let m = memory_at(36.8000, 10.1800, 200.0);
        let d = within_unlock_radius(36.8005, 10.1800, &m).expect("should be inside");
        assert!(d > 0.0 && d < 200.0, "distance was {d}");
    }

    #[test]
    fn outside_the_radius_is_rejected_with_the_distance() {
        let m = memory_at(36.8000, 10.1800, 200.0);
        // ~0.01 deg of latitude is ~1.1 km.
        let err = within_unlock_radius(36.8100, 10.1800, &m).expect_err("should be outside");
        assert!(err > 200.0, "distance was {err}");
    }

    #[test]
    fn exactly_on_the_pin_is_zero_metres() {
        let m = memory_at(36.8000, 10.1800, 200.0);
        let d = within_unlock_radius(36.8000, 10.1800, &m).unwrap();
        assert!(d < 1.0, "distance was {d}");
    }

    #[test]
    fn haversine_matches_a_known_long_distance() {
        // Tunis -> Sfax is roughly 238 km straight line.
        let d = haversine_m(36.8065, 10.1815, 34.7406, 10.7603);
        assert!(
            (d - 238_000.0).abs() < 5_000.0,
            "expected ~238 km, got {:.1} km",
            d / 1000.0
        );
    }

    #[test]
    fn redacted_json_never_carries_media_url() {
        let m = memory_at(36.8, 10.2, 200.0);
        let v = memory_to_json_redacted(&m);
        assert!(
            v.get("media_url").is_none(),
            "redacted view leaked media_url"
        );
        assert_eq!(v.get("locked"), Some(&json!(true)));
        assert_eq!(v.get("unlock_radius_m"), Some(&json!(200.0)));

        let full = memory_to_json(&m);
        assert_eq!(
            full.get("media_url").and_then(|v| v.as_str()),
            Some("https://media.bledi.tn/x.jpg")
        );
        assert_eq!(full.get("locked"), Some(&json!(false)));
    }

    #[test]
    fn unique_violation_detection_ignores_message_text() {
        // A generic error whose text happens to say "duplicate key" must NOT be
        // treated as a unique violation — that was the old, fragile behaviour.
        let e = sqlx::Error::Protocol("duplicate key value violates unique constraint".into());
        assert!(!is_unique_violation(&e));
    }

    #[test]
    fn unlock_rate_limit_key_is_per_user() {
        let a = Uuid::new_v4();
        let b = Uuid::new_v4();
        assert_ne!(format!("unlock:{a}"), format!("unlock:{b}"));
    }

    #[test]
    fn rate_limiter_denies_after_the_unlock_allowance() {
        let rl = RateLimiter::new();
        let unlock = crate::ratelimit::UNLOCK;
        for _ in 0..unlock.max_hits {
            assert_eq!(rl.check("unlock:x", unlock), Decision::Allow);
        }
        assert!(matches!(
            rl.check("unlock:x", unlock),
            Decision::Deny { .. }
        ));
    }
}
