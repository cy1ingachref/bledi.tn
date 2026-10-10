use axum::extract::{Path, Query, State};
use axum::http::StatusCode;
use axum::Json;
use bledi_core::*;
use serde_json::{json, Value};
use uuid::Uuid;

use crate::auth::{AuthError, AuthUser};
use crate::state::AppState;

// ── Health ──────────────────────────────────────────────────────────────────

pub async fn health() -> Json<Value> {
    Json(json!({ "status": "ok", "service": "bledi-server", "version": "0.1.0" }))
}

// ── Auth helpers ────────────────────────────────────────────────────────────

fn err(e: sqlx::Error) -> (StatusCode, Json<Value>) {
    (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({ "error": e.to_string() })))
}

fn hash_password(pw: &str) -> Result<String, AuthError> {
    bcrypt::hash(pw, bcrypt::DEFAULT_COST).map_err(|e| AuthError(e.to_string()))
}

fn verify_password(pw: &str, hash: &str) -> Result<bool, AuthError> {
    bcrypt::verify(pw, hash).map_err(|e| AuthError(e.to_string()))
}

// ── Auth handlers ───────────────────────────────────────────────────────────

pub async fn register(
    State(state): State<AppState>,
    Json(req): Json<RegisterRequest>,
) -> Result<Json<AuthResponse>, (StatusCode, Json<Value>)> {
    let hash = hash_password(&req.password).map_err(|e| {
        (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({ "error": e.0 })))
    })?;
    let user = sqlx::query_as!(
        User,
        r#"INSERT INTO users (email, password_hash, display_name)
           VALUES ($1, $2, $3)
           RETURNING id, email, password_hash, display_name, created_at"#,
        req.email, hash, req.display_name,
    )
    .fetch_one(&state.pool)
    .await
    .map_err(|e| {
        if e.to_string().contains("duplicate key") {
            (StatusCode::CONFLICT, Json(json!({ "error": "Email already registered" })))
        } else {
            err(e)
        }
    })?;

    let token = crate::auth::generate_token(&user).map_err(|e| {
        (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({ "error": e.0 })))
    })?;
    Ok(Json(AuthResponse { token, user: user.into() }))
}

pub async fn login(
    State(state): State<AppState>,
    Json(req): Json<LoginRequest>,
) -> Result<Json<AuthResponse>, (StatusCode, Json<Value>)> {
    let user = sqlx::query_as!(
        User,
        "SELECT id, email, password_hash, display_name, created_at FROM users WHERE email = $1",
        req.email,
    )
    .fetch_optional(&state.pool)
    .await
    .map_err(err)?
    .ok_or_else(|| (StatusCode::UNAUTHORIZED, Json(json!({ "error": "Invalid credentials" }))))?;

    if !verify_password(&req.password, &user.password_hash).map_err(|e| {
        (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({ "error": e.0 })))
    })? {
        return Err((StatusCode::UNAUTHORIZED, Json(json!({ "error": "Invalid credentials" }))));
    }

    let token = crate::auth::generate_token(&user).map_err(|e| {
        (StatusCode::INTERNAL_SERVER_ERROR, Json(json!({ "error": e.0 })))
    })?;
    Ok(Json(AuthResponse { token, user: user.into() }))
}

pub async fn get_me(
    State(state): State<AppState>,
    auth: AuthUser,
) -> Result<Json<PublicUser>, (StatusCode, Json<Value>)> {
    let user = sqlx::query_as!(
        User,
        "SELECT id, email, password_hash, display_name, created_at FROM users WHERE id = $1",
        auth.user_id,
    )
    .fetch_optional(&state.pool)
    .await
    .map_err(err)?
    .ok_or_else(|| (StatusCode::NOT_FOUND, Json(json!({ "error": "User not found" }))))?;

    Ok(Json(user.into()))
}

// ── Station handlers ────────────────────────────────────────────────────────

#[derive(Debug, serde::Deserialize)]
pub struct StationNearQuery {
    pub lat: f64,
    pub lon: f64,
    pub radius_m: Option<f64>,
}

pub async fn list_stations(
    State(state): State<AppState>,
) -> Result<Json<Vec<Station>>, (StatusCode, Json<Value>)> {
    let rows = sqlx::query!("SELECT id, name, lat, lon, modes, city FROM stations")
        .fetch_all(&state.pool)
        .await
        .map_err(err)?;

    let stations = rows
        .into_iter()
        .map(|r| {
            let modes: Vec<TransportMode> = r
                .modes
                .unwrap_or_default()
                .into_iter()
                .filter_map(|m| TransportMode::parse(m.as_str()))
                .collect();
            Station { id: r.id, name: r.name, lat: r.lat, lon: r.lon, modes, city: r.city }
        })
        .collect();

    Ok(Json(stations))
}

pub async fn nearby_stations(
    State(state): State<AppState>,
    Query(query): Query<StationNearQuery>,
) -> Result<Json<Vec<Station>>, (StatusCode, Json<Value>)> {
    let radius = query.radius_m.unwrap_or(2000.0);
    let rows = sqlx::query!(
        r#"SELECT id, name, lat, lon, modes, city,
                  earth_distance(ll_to_earth(lat, lon), ll_to_earth($1, $2)) AS dist_m
           FROM stations
           WHERE earth_box(ll_to_earth($1, $2), $3) @> ll_to_earth(lat, lon)
             AND earth_distance(ll_to_earth(lat, lon), ll_to_earth($1, $2)) <= $3
           ORDER BY dist_m
           LIMIT 100"#,
        query.lat, query.lon, radius,
    )
    .fetch_all(&state.pool)
    .await
    .map_err(err)?;

    let stations = rows
        .into_iter()
        .map(|r| {
            let modes: Vec<TransportMode> = r
                .modes
                .unwrap_or_default()
                .into_iter()
                .filter_map(|m| TransportMode::parse(m.as_str()))
                .collect();
            Station { id: r.id, name: r.name, lat: r.lat, lon: r.lon, modes, city: r.city }
        })
        .collect();

    Ok(Json(stations))
}

pub async fn get_station(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Station>, (StatusCode, Json<Value>)> {
    let row = sqlx::query!("SELECT id, name, lat, lon, modes, city FROM stations WHERE id = $1", id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| (StatusCode::NOT_FOUND, Json(json!({ "error": "Station not found" }))))?;

    let modes: Vec<TransportMode> = row
        .modes
        .unwrap_or_default()
        .into_iter()
        .filter_map(|m| TransportMode::parse(m.as_str()))
        .collect();

    Ok(Json(Station { id: row.id, name: row.name, lat: row.lat, lon: row.lon, modes, city: row.city }))
}

// ── Line handlers ───────────────────────────────────────────────────────────

pub async fn list_lines(
    State(state): State<AppState>,
) -> Result<Json<Vec<Line>>, (StatusCode, Json<Value>)> {
    let rows = sqlx::query!("SELECT id, number, name, mode, operator, color, station_ids FROM lines")
        .fetch_all(&state.pool)
        .await
        .map_err(err)?;

    let lines = rows
        .into_iter()
        .map(|r| Line {
            id: r.id,
            number: r.number,
            name: r.name,
            mode: TransportMode::parse(r.mode.as_str()).unwrap_or(TransportMode::Bus),
            operator: r.operator,
            color: r.color,
            station_ids: r.station_ids.unwrap_or_default(),
        })
        .collect();

    Ok(Json(lines))
}

pub async fn get_line(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Line>, (StatusCode, Json<Value>)> {
    let row = sqlx::query!("SELECT id, number, name, mode, operator, color, station_ids FROM lines WHERE id = $1", id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| (StatusCode::NOT_FOUND, Json(json!({ "error": "Line not found" }))))?;

    Ok(Json(Line {
        id: row.id,
        number: row.number,
        name: row.name,
        mode: TransportMode::parse(row.mode.as_str()).unwrap_or(TransportMode::Bus),
        operator: row.operator,
        color: row.color,
        station_ids: row.station_ids.unwrap_or_default(),
    }))
}

// ── Memory helpers ──────────────────────────────────────────────────────────

fn memory_from_row(row: sqlx::postgres::PgRow) -> Result<Memory, sqlx::Error> {
    use sqlx::Row;
    let mode_str: String = row.try_get("media_type")?;
    let vis_str: String = row.try_get("visibility")?;
    Ok(Memory {
        id: row.try_get("id")?,
        user_id: row.try_get("user_id")?,
        lat: row.try_get("lat")?,
        lon: row.try_get("lon")?,
        title: row.try_get("title")?,
        description: row.try_get("description")?,
        media_url: row.try_get("media_url")?,
        media_type: match mode_str.as_str() {
            "image" => MediaType::Image,
            "video" => MediaType::Video,
            _ => MediaType::Image,
        },
        visibility: match vis_str.as_str() {
            "public" => Visibility::Public,
            "friends" => Visibility::Friends,
            "private" => Visibility::Private,
            _ => Visibility::Public,
        },
        unlock_radius_m: row.try_get("unlock_radius_m")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn memory_to_json(m: &Memory) -> serde_json::Value {
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
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    })
}

// ── Memory handlers ─────────────────────────────────────────────────────────

pub async fn list_memories(
    State(state): State<AppState>,
    auth: AuthUser,
) -> Result<Json<Vec<serde_json::Value>>, (StatusCode, Json<Value>)> {
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
) -> Result<Json<Vec<serde_json::Value>>, (StatusCode, Json<Value>)> {
    let radius = query.radius_m.unwrap_or(500.0);
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
    .bind(query.lat)
    .bind(query.lon)
    .bind(radius)
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

pub async fn create_memory(
    State(state): State<AppState>,
    auth: AuthUser,
    Json(req): Json<CreateMemoryRequest>,
) -> Result<(StatusCode, Json<serde_json::Value>), (StatusCode, Json<Value>)> {
    let vis_str = match req.visibility {
        Visibility::Public => "public",
        Visibility::Friends => "friends",
        Visibility::Private => "private",
    };
    let row = sqlx::query(
        r#"INSERT INTO memories (user_id, lat, lon, title, description, media_url, media_type, visibility, unlock_radius_m)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *"#,
    )
    .bind(auth.user_id)
    .bind(req.lat)
    .bind(req.lon)
    .bind(req.title)
    .bind(req.description)
    .bind(req.media_url)
    .bind(req.media_type.as_str())
    .bind(vis_str)
    .bind(req.unlock_radius_m)
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
) -> Result<Json<serde_json::Value>, (StatusCode, Json<Value>)> {
    let row = sqlx::query("SELECT * FROM memories WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| (StatusCode::NOT_FOUND, Json(json!({ "error": "Memory not found" }))))?;

    let memory = memory_from_row(row).map_err(err)?;

    if memory.visibility == Visibility::Private && memory.user_id != auth.user_id {
        return Err((StatusCode::FORBIDDEN, Json(json!({ "error": "Access denied" }))));
    }

    Ok(Json(memory_to_json(&memory)))
}

pub async fn update_memory(
    State(state): State<AppState>,
    auth: AuthUser,
    Path(id): Path<Uuid>,
    Json(req): Json<UpdateMemoryRequest>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<Value>)> {
    let existing = sqlx::query("SELECT user_id FROM memories WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| (StatusCode::NOT_FOUND, Json(json!({ "error": "Memory not found" }))))?;

    use sqlx::Row;
    let owner_id: Uuid = existing.try_get("user_id").map_err(err)?;
    if owner_id != auth.user_id {
        return Err((StatusCode::FORBIDDEN, Json(json!({ "error": "Access denied" }))));
    }

    let row = sqlx::query("SELECT * FROM memories WHERE id = $1")
        .bind(id)
        .fetch_one(&state.pool)
        .await
        .map_err(err)?;
    let current = memory_from_row(row).map_err(err)?;

    let title = req.title.or(current.title);
    let description = req.description.or(current.description);
    let visibility = req.visibility.unwrap_or(current.visibility);
    let unlock_radius_m = req.unlock_radius_m.unwrap_or(current.unlock_radius_m);

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
        return Err((StatusCode::NOT_FOUND, Json(json!({ "error": "Memory not found" }))));
    }
    Ok(StatusCode::NO_CONTENT)
}

// ── Favorite handlers ───────────────────────────────────────────────────────

fn favorite_from_row(row: sqlx::postgres::PgRow) -> Result<Favorite, sqlx::Error> {
    use sqlx::Row;
    let kind_str: String = row.try_get("kind")?;
    Ok(Favorite {
        id: row.try_get("id")?,
        user_id: row.try_get("user_id")?,
        kind: match kind_str.as_str() {
            "station" => FavoriteKind::Station,
            "line" => FavoriteKind::Line,
            "place" => FavoriteKind::Place,
            _ => FavoriteKind::Place,
        },
        ref_id: row.try_get("ref_id")?,
        label: row.try_get("label")?,
        created_at: row.try_get("created_at")?,
    })
}

fn favorite_to_json(f: &Favorite) -> serde_json::Value {
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
) -> Result<Json<Vec<serde_json::Value>>, (StatusCode, Json<Value>)> {
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
) -> Result<(StatusCode, Json<serde_json::Value>), (StatusCode, Json<Value>)> {
    let kind_str = req.kind.as_str();
    let row = sqlx::query(
        r#"INSERT INTO favorites (user_id, kind, ref_id, label)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (user_id, kind, ref_id) DO UPDATE SET label = EXCLUDED.label
           RETURNING *"#,
    )
    .bind(auth.user_id)
    .bind(kind_str)
    .bind(req.ref_id)
    .bind(req.label)
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
        return Err((StatusCode::NOT_FOUND, Json(json!({ "error": "Favorite not found" }))));
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

fn share_to_json(s: &LocationShare) -> serde_json::Value {
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
) -> Result<Json<Vec<serde_json::Value>>, (StatusCode, Json<Value>)> {
    let rows = sqlx::query("SELECT * FROM location_shares WHERE user_id = $1 ORDER BY updated_at DESC")
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
) -> Result<Json<Vec<serde_json::Value>>, (StatusCode, Json<Value>)> {
    let radius = query.radius_m.unwrap_or(5000.0);
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
    .bind(query.lat)
    .bind(query.lon)
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
) -> Result<(StatusCode, Json<serde_json::Value>), (StatusCode, Json<Value>)> {
    let row = sqlx::query(
        r#"INSERT INTO location_shares (user_id, lat, lon, accuracy_m, note, is_active, expires_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *"#,
    )
    .bind(auth.user_id)
    .bind(req.lat)
    .bind(req.lon)
    .bind(req.accuracy_m)
    .bind(req.note)
    .bind(req.is_active)
    .bind(req.expires_at)
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
) -> Result<Json<serde_json::Value>, (StatusCode, Json<Value>)> {
    let existing = sqlx::query("SELECT user_id FROM location_shares WHERE id = $1")
        .bind(id)
        .fetch_optional(&state.pool)
        .await
        .map_err(err)?
        .ok_or_else(|| (StatusCode::NOT_FOUND, Json(json!({ "error": "Location share not found" }))))?;

    use sqlx::Row;
    let owner_id: Uuid = existing.try_get("user_id").map_err(err)?;
    if owner_id != auth.user_id {
        return Err((StatusCode::FORBIDDEN, Json(json!({ "error": "Access denied" }))));
    }

    let row = sqlx::query(
        r#"UPDATE location_shares
           SET lat=$1, lon=$2, accuracy_m=$3, note=$4, is_active=$5, expires_at=$6, updated_at=now()
           WHERE id=$7 RETURNING *"#,
    )
    .bind(req.lat)
    .bind(req.lon)
    .bind(req.accuracy_m)
    .bind(req.note)
    .bind(req.is_active)
    .bind(req.expires_at)
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
        return Err((StatusCode::NOT_FOUND, Json(json!({ "error": "Location share not found" }))));
    }
    Ok(StatusCode::NO_CONTENT)
}
