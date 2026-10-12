pub mod auth;
pub mod handlers;
pub mod ratelimit;
pub mod state;
pub mod validate;

use axum::http::{HeaderValue, Method};
use axum::routing::{delete, get, post, put};
use axum::Router;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

use crate::state::AppState;

/// CORS origins used when `ALLOWED_ORIGINS` is unset.
///
/// Localhost only, matching the Python backend's defaults. A wildcard origin is
/// never a sensible default for an API that carries a bearer token.
pub const DEFAULT_ALLOWED_ORIGINS: &[&str] = &[
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
];

/// Parse a comma-separated origin list, skipping (and reporting) invalid entries.
///
/// Skipping rather than panicking keeps a typo in one origin from taking the
/// whole service down, but the warning makes it visible instead of silent.
///
/// Note that `HeaderValue::from_str` alone is NOT a sufficient check: a space is
/// a legal character in a header value, so `"not a url"` parses fine. An entry
/// that is not actually an origin would never match a real `Origin` header, so
/// it fails closed — but the operator would never learn about the typo. The
/// shape check below makes the mistake loud.
pub fn parse_allowed_origins(raw: &str) -> Vec<HeaderValue> {
    raw.split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .filter_map(|s| {
            if s == "*" {
                // A wildcard origin on an API that carries a bearer token is
                // never intended. Refuse it rather than shipping an open policy.
                tracing::warn!(
                    "ignoring CORS origin '*': wildcard origins are not allowed. \
                     List the origins explicitly in ALLOWED_ORIGINS."
                );
                return None;
            }
            let lower = s.to_ascii_lowercase();
            if !(lower.starts_with("http://") || lower.starts_with("https://")) {
                tracing::warn!("ignoring CORS origin {s:?}: must start with http:// or https://");
                return None;
            }
            let after_scheme = &s[s.find("://").map(|i| i + 3).unwrap_or(s.len())..];
            let host = after_scheme.split('/').next().unwrap_or_default();
            if host.is_empty() || host.contains(char::is_whitespace) {
                tracing::warn!("ignoring CORS origin {s:?}: malformed host");
                return None;
            }
            match HeaderValue::from_str(s) {
                Ok(v) => Some(v),
                Err(_) => {
                    tracing::warn!("ignoring invalid CORS origin: {s:?}");
                    None
                }
            }
        })
        .collect()
}

/// Origins from `ALLOWED_ORIGINS`, falling back to [`DEFAULT_ALLOWED_ORIGINS`].
pub fn allowed_origins_from_env() -> Vec<HeaderValue> {
    match std::env::var("ALLOWED_ORIGINS") {
        Ok(raw) if !raw.trim().is_empty() => parse_allowed_origins(&raw),
        _ => parse_allowed_origins(&DEFAULT_ALLOWED_ORIGINS.join(",")),
    }
}

pub fn router(state: AppState) -> Router {
    // Explicit allow-lists. No `Any` on origins, methods or headers.
    //
    // Credentials are NOT enabled: the API authenticates with a bearer token in
    // the Authorization header, which the browser does not attach
    // automatically, so `allow_credentials` is unnecessary. Leaving it off also
    // means this layer can never be combined with a wildcard origin, which
    // browsers reject and which is a common way to ship an open CORS policy by
    // accident.
    let cors = CorsLayer::new()
        .allow_origin(state.allowed_origins.as_ref().clone())
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PUT,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers([
            axum::http::header::AUTHORIZATION,
            axum::http::header::CONTENT_TYPE,
        ]);

    Router::new()
        .route("/api/v1/health", get(handlers::health))
        .route("/api/v1/auth/register", post(handlers::register))
        .route("/api/v1/auth/login", post(handlers::login))
        .route("/api/v1/stations", get(handlers::list_stations))
        .route("/api/v1/stations/near", get(handlers::nearby_stations))
        .route("/api/v1/stations/:id", get(handlers::get_station))
        .route("/api/v1/lines", get(handlers::list_lines))
        .route("/api/v1/lines/:id", get(handlers::get_line))
        .route(
            "/api/v1/memories",
            get(handlers::list_memories).post(handlers::create_memory),
        )
        .route("/api/v1/memories/nearby", get(handlers::nearby_memories))
        .route(
            "/api/v1/memories/:id",
            get(handlers::get_memory)
                .put(handlers::update_memory)
                .delete(handlers::delete_memory),
        )
        .route("/api/v1/memories/:id/unlock", post(handlers::unlock_memory))
        .route(
            "/api/v1/favorites",
            get(handlers::list_favorites).post(handlers::create_favorite),
        )
        .route("/api/v1/favorites/:id", delete(handlers::delete_favorite))
        .route("/api/v1/friendships", get(handlers::list_friendships))
        .route(
            "/api/v1/friendships/requests",
            get(handlers::list_friend_requests),
        )
        .route(
            "/api/v1/friendships/request",
            post(handlers::request_friendship),
        )
        .route(
            "/api/v1/friendships/accept",
            post(handlers::accept_friendship),
        )
        .route(
            "/api/v1/friendships/:user_id",
            delete(handlers::delete_friendship),
        )
        .route(
            "/api/v1/location-shares",
            get(handlers::list_location_shares).post(handlers::create_location_share),
        )
        .route(
            "/api/v1/location-shares/nearby",
            get(handlers::nearby_location_shares),
        )
        .route(
            "/api/v1/location-shares/:id",
            put(handlers::update_location_share).delete(handlers::delete_location_share),
        )
        .route("/api/v1/users/me", get(handlers::get_me))
        .layer(cors)
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_localhost_only() {
        let origins = parse_allowed_origins(&DEFAULT_ALLOWED_ORIGINS.join(","));
        assert_eq!(origins.len(), DEFAULT_ALLOWED_ORIGINS.len());
        for o in &origins {
            let s = o.to_str().unwrap();
            assert!(
                s.starts_with("http://127.0.0.1:") || s.starts_with("http://localhost:"),
                "unexpected default origin {s}"
            );
        }
    }

    #[test]
    fn invalid_origins_are_skipped_not_fatal() {
        let origins =
            parse_allowed_origins("http://ok.example.com,not a url,http://also.example.com");
        assert_eq!(origins.len(), 2, "only the two real origins should survive");
    }

    #[test]
    fn schemeless_origins_are_rejected() {
        // `HeaderValue::from_str` accepts these (a space is legal in a header
        // value), so the shape check is what actually rejects them.
        let origins = parse_allowed_origins("example.com,localhost:5173,http://good.example.com");
        assert_eq!(origins.len(), 1);
        assert_eq!(origins[0].to_str().unwrap(), "http://good.example.com");
    }

    #[test]
    fn wildcard_origin_is_refused() {
        let origins = parse_allowed_origins("*,http://good.example.com");
        assert_eq!(origins.len(), 1, "the wildcard must be dropped");
        assert_eq!(origins[0].to_str().unwrap(), "http://good.example.com");
    }

    #[test]
    fn wildcard_is_not_in_the_defaults() {
        let origins = parse_allowed_origins(&DEFAULT_ALLOWED_ORIGINS.join(","));
        assert!(
            !origins.iter().any(|o| o.to_str().ok() == Some("*")),
            "the default origin list must never contain a wildcard"
        );
    }
}
