use axum::extract::State;
use axum::http::StatusCode;
use bledi_application::favorites::SaveFavorite;
use bledi_application::friendships::{Friend, FriendEmail, FriendshipChange};
use bledi_application::location_shares::ShareLocation;
use bledi_application::Nearby;
use bledi_domain::favorite::Favorite;
use bledi_domain::friendship::FriendshipStatus;
use bledi_domain::location_share::LocationShare;
use uuid::Uuid;

use crate::auth::AuthUser;
use crate::extract::{Json, Path, Query};
use crate::pagination::Pagination;
use crate::{ApiError, AppState};

type Created<T> = Result<(StatusCode, Json<T>), ApiError>;

pub async fn friends(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Query(pagination): Query<Pagination>,
) -> Result<Json<Vec<Friend>>, ApiError> {
    let (limit, offset) = pagination.into();
    Ok(Json(
        state
            .services
            .friendships
            .list_paginated(me, limit, offset)
            .await?,
    ))
}

pub async fn friend_requests(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Query(pagination): Query<Pagination>,
) -> Result<Json<Vec<Friend>>, ApiError> {
    let (limit, offset) = pagination.into();
    Ok(Json(
        state
            .services
            .friendships
            .requests_paginated(me, limit, offset)
            .await?,
    ))
}

/// 201 for a new request, 200 when it accepted the one the other user had already sent.
pub async fn request_friend(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Json(input): Json<FriendEmail>,
) -> Created<FriendshipChange> {
    let change = state.services.friendships.request(me, input).await?;
    let status = match change.status {
        FriendshipStatus::Pending => StatusCode::CREATED,
        _ => StatusCode::OK,
    };
    Ok((status, Json(change)))
}

pub async fn accept_friend(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Json(input): Json<FriendEmail>,
) -> Result<Json<FriendshipChange>, ApiError> {
    Ok(Json(state.services.friendships.accept(me, input).await?))
}

pub async fn remove_friend(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Path(other): Path<Uuid>,
) -> Result<StatusCode, ApiError> {
    state.services.friendships.remove(me, other).await?;
    Ok(StatusCode::NO_CONTENT)
}

pub async fn favorites(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Query(pagination): Query<Pagination>,
) -> Result<Json<Vec<Favorite>>, ApiError> {
    let (limit, offset) = pagination.into();
    Ok(Json(
        state
            .services
            .favorites
            .list_paginated(me, limit, offset)
            .await?,
    ))
}

pub async fn save_favorite(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Json(input): Json<SaveFavorite>,
) -> Created<Favorite> {
    let favorite = state.services.favorites.save(me, input).await?;
    Ok((StatusCode::CREATED, Json(favorite)))
}

pub async fn delete_favorite(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, ApiError> {
    state.services.favorites.delete(me, id).await?;
    Ok(StatusCode::NO_CONTENT)
}

pub async fn my_shares(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
) -> Result<Json<Vec<LocationShare>>, ApiError> {
    Ok(Json(state.services.location_shares.mine(me).await?))
}

pub async fn nearby_shares(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Query(query): Query<Nearby>,
) -> Result<Json<Vec<LocationShare>>, ApiError> {
    Ok(Json(
        state.services.location_shares.nearby(me, query).await?,
    ))
}

pub async fn share_location(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Json(input): Json<ShareLocation>,
) -> Created<LocationShare> {
    let share = state.services.location_shares.create(me, input).await?;
    Ok((StatusCode::CREATED, Json(share)))
}

pub async fn update_share(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Path(id): Path<Uuid>,
    Json(input): Json<ShareLocation>,
) -> Result<Json<LocationShare>, ApiError> {
    Ok(Json(
        state.services.location_shares.update(me, id, input).await?,
    ))
}

pub async fn delete_share(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    Path(id): Path<Uuid>,
) -> Result<StatusCode, ApiError> {
    state.services.location_shares.delete(me, id).await?;
    Ok(StatusCode::NO_CONTENT)
}
