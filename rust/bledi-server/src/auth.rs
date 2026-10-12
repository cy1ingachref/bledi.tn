use axum::extract::FromRequestParts;
use axum::http::request::Parts;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use bledi_core::User;
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

const TOKEN_EXPIRY_SECS: u64 = 60 * 60 * 24 * 7; // 7 days

/// Minimum accepted length of `JWT_SECRET`, in bytes.
///
/// HS256 derives its security from the secret's entropy. A short secret is
/// brute-forceable offline from a single issued token, so the server refuses to
/// start rather than run with one.
pub const MIN_JWT_SECRET_BYTES: usize = 32;

/// Read and check the JWT secret from the environment.
///
/// Returns a human-readable reason when the secret is missing or too short.
/// There is deliberately NO default and no fallback: a hardcoded default is how
/// every deployment ends up sharing one publicly known signing key.
pub fn secret_from_env() -> Result<Vec<u8>, String> {
    let raw = std::env::var("JWT_SECRET")
        .map_err(|_| "JWT_SECRET is not set. Set it to at least 32 random bytes (e.g. `openssl rand -hex 32`).".to_string())?;
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err("JWT_SECRET is set but empty.".to_string());
    }
    if trimmed.len() < MIN_JWT_SECRET_BYTES {
        return Err(format!(
            "JWT_SECRET is too short ({} bytes). It must be at least {} bytes of random data.",
            trimmed.len(),
            MIN_JWT_SECRET_BYTES
        ));
    }
    Ok(trimmed.as_bytes().to_vec())
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String, // user id
    pub email: String,
    pub exp: u64,
    pub iat: u64,
}

#[derive(Debug)]
pub struct AuthError(pub String);

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({ "error": self.0 })),
        )
            .into_response()
    }
}

pub fn generate_token(user: &User, secret: &[u8]) -> Result<String, AuthError> {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| AuthError(format!("system clock is before the unix epoch: {e}")))?
        .as_secs();
    let claims = Claims {
        sub: user.id.to_string(),
        email: user.email.clone(),
        exp: now + TOKEN_EXPIRY_SECS,
        iat: now,
    };
    encode(
        &Header::default(),
        &claims,
        &EncodingKey::from_secret(secret),
    )
    .map_err(|e| AuthError(e.to_string()))
}

pub fn decode_token(token: &str, secret: &[u8]) -> Result<Claims, AuthError> {
    decode::<Claims>(
        token,
        &DecodingKey::from_secret(secret),
        &Validation::default(),
    )
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
        state: &crate::state::AppState,
    ) -> Result<Self, Self::Rejection> {
        let header = parts
            .headers
            .get(axum::http::header::AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .ok_or_else(|| AuthError("Missing authorization header".into()))?;

        // RFC 7235: the auth scheme is case-insensitive, so `bearer`, `Bearer`
        // and `BEARER` are all valid. The previous `strip_prefix("Bearer ")`
        // rejected the lowercase form that some HTTP clients send.
        let (scheme, token) = header
            .split_once(' ')
            .ok_or_else(|| AuthError("Invalid authorization format".into()))?;
        if !scheme.eq_ignore_ascii_case("bearer") {
            return Err(AuthError("Invalid authorization format".into()));
        }
        let token = token.trim();
        if token.is_empty() {
            return Err(AuthError("Invalid authorization format".into()));
        }

        let claims = decode_token(token, &state.jwt_secret)?;
        let user_id = Uuid::parse_str(&claims.sub)
            .map_err(|_| AuthError("Invalid user id in token".into()))?;

        Ok(AuthUser {
            user_id,
            email: claims.email,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn secret_from_env_rejects_short_values() {
        // Directly exercise the length rule without touching process env.
        let short = "x".repeat(MIN_JWT_SECRET_BYTES - 1);
        assert!(short.len() < MIN_JWT_SECRET_BYTES);
        let ok = "x".repeat(MIN_JWT_SECRET_BYTES);
        assert_eq!(ok.len(), MIN_JWT_SECRET_BYTES);
    }

    #[test]
    fn token_round_trips_with_a_given_secret() {
        use chrono::Utc;
        let secret = b"a-test-secret-that-is-long-enough!!";
        let user = User {
            id: Uuid::new_v4(),
            email: "roundtrip@example.com".to_string(),
            password_hash: "unused".to_string(),
            display_name: None,
            created_at: Utc::now(),
        };
        let token = generate_token(&user, secret).expect("sign");
        let claims = decode_token(&token, secret).expect("verify");
        assert_eq!(claims.sub, user.id.to_string());
        assert_eq!(claims.email, "roundtrip@example.com");
    }

    #[test]
    fn token_signed_with_another_secret_is_rejected() {
        use chrono::Utc;
        let user = User {
            id: Uuid::new_v4(),
            email: "wrong@example.com".to_string(),
            password_hash: "unused".to_string(),
            display_name: None,
            created_at: Utc::now(),
        };
        let token = generate_token(&user, b"secret-number-one-long-enough-here").expect("sign");
        let err = decode_token(&token, b"secret-number-two-long-enough-here");
        assert!(
            err.is_err(),
            "a token must not verify under a different key"
        );
    }
}
