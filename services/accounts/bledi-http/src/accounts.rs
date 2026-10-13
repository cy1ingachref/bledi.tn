use std::net::SocketAddr;

use axum::extract::{ConnectInfo, State};
use axum::http::{HeaderMap, StatusCode};
use bledi_application::accounts::{Login, Register, Session};
use bledi_domain::user::User;
use serde_json::{json, Value};

use crate::auth::AuthUser;
use crate::extract::Json;
use crate::rate_limit::{client_ip, Decision, Limit};
use crate::{ApiError, AppState};

pub async fn health() -> Json<Value> {
    Json(json!({ "status": "ok", "service": "bledi-server", "version": "0.1.0" }))
}

fn limit_by_ip(
    state: &AppState,
    action: &str,
    limit: Limit,
    headers: &HeaderMap,
    peer: Option<ConnectInfo<SocketAddr>>,
) -> Result<(), ApiError> {
    let ip = client_ip(headers, peer.map(|c| c.0), state.trust_proxy_headers);
    match state.limiter.check(&format!("{action}:{ip}"), limit) {
        Decision::Allow => Ok(()),
        Decision::Deny { retry_after_secs } => Err(ApiError::RateLimited { retry_after_secs }),
    }
}

pub async fn register(
    State(state): State<AppState>,
    peer: Option<ConnectInfo<SocketAddr>>,
    headers: HeaderMap,
    Json(input): Json<Register>,
) -> Result<(StatusCode, Json<Session>), ApiError> {
    limit_by_ip(&state, "register", state.limits.register, &headers, peer)?;
    let session = state.services.accounts.register(input).await?;
    Ok((StatusCode::CREATED, Json(session)))
}

pub async fn login(
    State(state): State<AppState>,
    peer: Option<ConnectInfo<SocketAddr>>,
    headers: HeaderMap,
    Json(input): Json<Login>,
) -> Result<Json<Session>, ApiError> {
    limit_by_ip(&state, "login", state.limits.login, &headers, peer)?;
    Ok(Json(state.services.accounts.login(input).await?))
}

pub async fn me(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
) -> Result<Json<User>, ApiError> {
    Ok(Json(state.services.accounts.me(me).await?))
}
