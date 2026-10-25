mod accounts;
mod auth;
pub mod cors;
mod error;
mod exif;
mod extract;
pub mod media;
mod memories;
pub mod pagination;
pub mod rate_limit;
mod social;
mod upload;

use std::sync::Arc;

use axum::extract::DefaultBodyLimit;
use axum::http::HeaderValue;
use axum::routing::{delete, get, post, put};
use axum::Router;
use bledi_application::Services;
use tower_http::trace::TraceLayer;

pub use error::ApiError;
use media::MediaStore;
use rate_limit::{RateLimiter, RateLimits};

pub struct HttpConfig {
    pub allowed_origins: Vec<HeaderValue>,
    pub rate_limits: RateLimits,
    /// Take the client IP from `X-Forwarded-For`. Only behind a proxy that overwrites it.
    pub trust_proxy_headers: bool,
    /// Where uploaded photos are written and read from.
    pub media: MediaStore,
}

#[derive(Clone)]
pub struct AppState {
    services: Services,
    limiter: Arc<RateLimiter>,
    limits: RateLimits,
    trust_proxy_headers: bool,
    media: MediaStore,
}

pub fn router(services: Services, config: HttpConfig) -> Router {
    let state = AppState {
        services,
        limiter: Arc::default(),
        limits: config.rate_limits,
        trust_proxy_headers: config.trust_proxy_headers,
        media: config.media,
    };
    Router::new()
        .route("/api/v1/health", get(accounts::health))
        .route("/api/v1/auth/register", post(accounts::register))
        .route("/api/v1/auth/login", post(accounts::login))
        .route("/api/v1/users/me", get(accounts::me))
        .route(
            "/api/v1/memories",
            get(memories::mine)
                .post(memories::create)
                // The default body limit is 2 MB, which is below the size of a phone photo.
                .layer(DefaultBodyLimit::max(media::MAX_UPLOAD_BYTES + 1024 * 1024)),
        )
        .route("/api/v1/memories/nearby", get(memories::nearby))
        .route(
            "/api/v1/memories/:id",
            get(memories::get)
                .put(memories::update)
                .delete(memories::delete),
        )
        .route("/api/v1/memories/:id/unlock", post(memories::unlock))
        .route("/api/v1/media/:key", get(media::serve))
        .route("/api/v1/friendships", get(social::friends))
        .route("/api/v1/friendships/requests", get(social::friend_requests))
        .route("/api/v1/friendships/request", post(social::request_friend))
        .route("/api/v1/friendships/accept", post(social::accept_friend))
        .route(
            "/api/v1/friendships/:user_id",
            delete(social::remove_friend),
        )
        .route(
            "/api/v1/favorites",
            get(social::favorites).post(social::save_favorite),
        )
        .route("/api/v1/favorites/:id", delete(social::delete_favorite))
        .route(
            "/api/v1/location-shares",
            get(social::my_shares).post(social::share_location),
        )
        .route("/api/v1/location-shares/nearby", get(social::nearby_shares))
        .route(
            "/api/v1/location-shares/:id",
            put(social::update_share).delete(social::delete_share),
        )
        .layer(cors::layer(config.allowed_origins))
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}
