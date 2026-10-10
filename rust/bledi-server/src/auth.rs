use axum::extract::FromRequestParts;
use axum::http::request::Parts;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};
use bledi_core::User;
use uuid::Uuid;

const JWT_SECRET: &[u8] = b"REDACTED_DEV_SECRET";
const TOKEN_EXPIRY_SECS: u64 = 60 * 60 * 24 * 7; // 7 days

#[derive(Debug, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String,       // user id
    pub email: String,
    pub exp: u64,
    pub iat: u64,
}

#[derive(Debug)]
pub struct AuthError(pub String);

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        (StatusCode::UNAUTHORIZED, Json(serde_json::json!({ "error": self.0 }))).into_response()
    }
}

pub fn generate_token(user: &User) -> Result<String, AuthError> {
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs();
    let claims = Claims {
        sub: user.id.to_string(),
        email: user.email.clone(),
        exp: now + TOKEN_EXPIRY_SECS,
        iat: now,
    };
    encode(&Header::default(), &claims, &EncodingKey::from_secret(JWT_SECRET))
        .map_err(|e| AuthError(e.to_string()))
}

pub fn decode_token(token: &str) -> Result<Claims, AuthError> {
    decode::<Claims>(token, &DecodingKey::from_secret(JWT_SECRET), &Validation::default())
        .map(|d| d.claims)
        .map_err(|e| AuthError(e.to_string()))
}

pub struct AuthUser {
    pub user_id: Uuid,
    pub email: String,
}

#[async_trait::async_trait]
impl FromRequestParts<crate::state::AppState> for AuthUser {
    type Rejection = AuthError;

    async fn from_request_parts(
        parts: &mut Parts,
        _state: &crate::state::AppState,
    ) -> Result<Self, Self::Rejection> {
        let header = parts
            .headers
            .get(axum::http::header::AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .ok_or_else(|| AuthError("Missing authorization header".into()))?;

        let token = header
            .strip_prefix("Bearer ")
            .ok_or_else(|| AuthError("Invalid authorization format".into()))?;

        let claims = decode_token(token)?;
        let user_id = Uuid::parse_str(&claims.sub)
            .map_err(|_| AuthError("Invalid user id in token".into()))?;

        Ok(AuthUser {
            user_id,
            email: claims.email,
        })
    }
}
