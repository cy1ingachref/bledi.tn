use axum::async_trait;
use axum::extract::FromRequestParts;
use axum::http::header::AUTHORIZATION;
use axum::http::request::Parts;
use bledi_application::AppError;
use uuid::Uuid;

use crate::{ApiError, AppState};

/// The caller, identified by a bearer token.
pub struct AuthUser(pub Uuid);

#[async_trait]
impl FromRequestParts<AppState> for AuthUser {
    type Rejection = ApiError;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, ApiError> {
        let header = parts
            .headers
            .get(AUTHORIZATION)
            .ok_or(AppError::Unauthorized("Missing authorization header"))?;
        let token = header
            .to_str()
            .ok()
            .and_then(|value| value.split_once(' '))
            .filter(|(scheme, _)| scheme.eq_ignore_ascii_case("bearer"))
            .map(|(_, token)| token.trim())
            .filter(|token| !token.is_empty())
            .ok_or(AppError::Unauthorized("Invalid authorization format"))?;
        Ok(Self(state.services.accounts.authenticate(token)?))
    }
}
