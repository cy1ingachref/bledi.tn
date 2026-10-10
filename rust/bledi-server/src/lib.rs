pub mod auth;
pub mod handlers;
pub mod state;

use axum::routing::{delete, get, post, put};
use axum::Router;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;

use crate::state::AppState;

pub fn router(state: AppState) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

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
        .route(
            "/api/v1/favorites",
            get(handlers::list_favorites).post(handlers::create_favorite),
        )
        .route("/api/v1/favorites/:id", delete(handlers::delete_favorite))
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
