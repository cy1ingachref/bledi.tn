use axum::extract::State;
use axum::http::StatusCode;
use bledi_application::memories::UpdateMemory;
use bledi_application::{Nearby, Position};
use bledi_domain::memory::{MediaType, Memory, Visibility};
use chrono::{DateTime, Utc};
use serde::Serialize;
use uuid::Uuid;

use crate::auth::AuthUser;
use crate::extract::{Json, Path, Query};
use crate::media;
use crate::rate_limit::Decision;
use crate::upload::CreateMemoryBody;
use crate::{ApiError, AppState};

/// A memory as its owner, or a caller who unlocked it, sees it.
#[derive(Serialize)]
pub struct MemoryView {
    #[serde(flatten)]
    summary: MemorySummary,
    media_url: String,
}

/// A memory without its media, for discovery. `locked` tells a client the media exists but is
/// withheld, as opposed to missing.
#[derive(Serialize)]
pub struct MemorySummary {
    id: Uuid,
    user_id: Uuid,
    lat: f64,
    lon: f64,
    title: Option<String>,
    description: Option<String>,
    media_type: MediaType,
    visibility: Visibility,
    unlock_radius_m: f64,
    locked: bool,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

#[derive(Serialize)]
pub struct UnlockedView {
    #[serde(flatten)]
    memory: MemoryView,
    distance_m: f64,
}

fn summary(m: Memory, locked: bool) -> (MemorySummary, String) {
    let summary = MemorySummary {
        id: m.id,
        user_id: m.user_id,
        lat: m.lat,
        lon: m.lon,
        title: m.title,
        description: m.description,
        media_type: m.media_type,
        visibility: m.visibility,
        unlock_radius_m: m.unlock_radius_m,
        locked,
        created_at: m.created_at,
        updated_at: m.updated_at,
    };
    (summary, m.media_url)
}

impl From<Memory> for MemoryView {
    fn from(m: Memory) -> Self {
        let (summary, media_url) = summary(m, false);
        Self { summary, media_url }
    }
}

impl From<Memory> for MemorySummary {
    fn from(m: Memory) -> Self {
        summary(m, true).0
    }
}

fn views<T: From<Memory>>(memories: Vec<Memory>) -> Json<Vec<T>> {
    Json(memories.into_iter().map(T::from).collect())
}

pub async fn mine(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
) -> Result<Json<Vec<MemoryView>>, ApiError> {
    Ok(views(state.services.memories.mine(me).await?))
}

pub async fn nearby(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Query(query): Query<Nearby>,
) -> Result<Json<Vec<MemorySummary>>, ApiError> {
    Ok(views(state.services.memories.nearby(me, query).await?))
}

/// Creates a memory. The request is JSON, or a form carrying a photo.
///
/// An uploaded photo is stored under the media root and the memory points at it by key, so
/// the URL is derived from the key and the client never names the file.
pub async fn create(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    body: CreateMemoryBody,
) -> Result<(StatusCode, Json<MemoryView>), ApiError> {
    let (input, uploaded) = match body.photo {
        Some(photo) => {
            let prepared = media::prepare(&photo)?;
            state.media.save(&prepared.key, &prepared.bytes).await?;
            let mut input = body.memory;
            input.media_key = Some(prepared.key.clone());
            input.media_url = None;
            // The type comes from the bytes, not from what the client called it.
            input.media_type = MediaType::Image;
            (input, Some(prepared))
        }
        None => (body.memory, None),
    };

    let memory = match state.services.memories.create(me, input).await {
        Ok(memory) => memory,
        Err(e) => {
            // The photo has no memory to belong to, so it must not stay behind.
            if let Some(prepared) = uploaded {
                state.media.remove(&prepared.key).await;
            }
            return Err(e.into());
        }
    };
    Ok((StatusCode::CREATED, Json(memory.into())))
}

#[derive(Serialize)]
#[serde(untagged)]
pub enum MemoryOrSummary {
    Memory(MemoryView),
    Summary(MemorySummary),
}

/// Only the owner gets the media here; anyone else goes through `unlock` and its radius.
pub async fn get(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Path(id): Path<Uuid>,
) -> Result<Json<MemoryOrSummary>, ApiError> {
    let memory = state.services.memories.get(me, id).await?;
    Ok(Json(if memory.user_id == me {
        MemoryOrSummary::Memory(memory.into())
    } else {
        MemoryOrSummary::Summary(memory.into())
    }))
}

pub async fn update(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Path(id): Path<Uuid>,
    Json(input): Json<UpdateMemory>,
) -> Result<Json<MemoryView>, ApiError> {
    Ok(Json(
        state.services.memories.update(me, id, input).await?.into(),
    ))
}

pub async fn delete(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, ApiError> {
    state.services.memories.delete(me, id).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Rate limited per user rather than per IP: unlocking spends the user's allowance, and many
/// users can share one IP behind NAT.
pub async fn unlock(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Path(id): Path<Uuid>,
    Json(at): Json<Position>,
) -> Result<Json<UnlockedView>, ApiError> {
    if let Decision::Deny { retry_after_secs } = state
        .limiter
        .check(&format!("unlock:{me}"), state.limits.unlock)
    {
        return Err(ApiError::RateLimited { retry_after_secs });
    }
    let unlocked = state.services.memories.unlock(me, id, at).await?;
    Ok(Json(UnlockedView {
        memory: unlocked.memory.into(),
        distance_m: unlocked.distance_m.round(),
    }))
}
