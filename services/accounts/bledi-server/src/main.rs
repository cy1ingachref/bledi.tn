mod config;
mod jwt;
mod password;

use std::net::SocketAddr;
use std::sync::Arc;

use bledi_application::ports::Clock;
use bledi_application::{Ports, Services};
use bledi_http::rate_limit::RateLimits;
use bledi_http::HttpConfig;
use bledi_postgres::{
    PostgresFavoriteStore, PostgresFriendshipStore, PostgresLocationShareStore,
    PostgresMemoryStore, PostgresUserStore, MIGRATOR,
};
use chrono::{DateTime, Utc};
use sqlx::postgres::PgPoolOptions;
use tracing_subscriber::EnvFilter;

use crate::config::Config;
use crate::jwt::JwtTokenIssuer;
use crate::password::BcryptPasswordHasher;

struct SystemClock;

impl Clock for SystemClock {
    fn now(&self) -> DateTime<Utc> {
        Utc::now()
    }
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .with_target(false)
        .init();
    let _ = dotenvy::dotenv();

    let config = Config::from_env().unwrap_or_else(|reason| {
        eprintln!("FATAL: refusing to start: {reason}");
        std::process::exit(1);
    });

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&config.database_url)
        .await
        .expect("connect to the database");
    MIGRATOR.run(&pool).await.expect("run the migrations");

    let ports = Ports {
        users: Arc::new(PostgresUserStore::new(pool.clone())),
        memories: Arc::new(PostgresMemoryStore::new(pool.clone())),
        friendships: Arc::new(PostgresFriendshipStore::new(pool.clone())),
        favorites: Arc::new(PostgresFavoriteStore::new(pool.clone())),
        location_shares: Arc::new(PostgresLocationShareStore::new(pool)),
        hasher: Arc::new(BcryptPasswordHasher),
        tokens: Arc::new(JwtTokenIssuer::new(&config.jwt_secret)),
        clock: Arc::new(SystemClock),
    };
    tracing::info!("CORS: {} allowed origin(s)", config.allowed_origins.len());
    let app = bledi_http::router(
        Services::new(&ports),
        HttpConfig {
            allowed_origins: config.allowed_origins,
            rate_limits: RateLimits::default(),
            trust_proxy_headers: config.trust_proxy_headers,
        },
    );

    let addr = SocketAddr::from(([0, 0, 0, 0], 3000));
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("bind the listen address");
    tracing::info!("bledi-server listening on {addr}");
    // The peer address keys the per-IP rate limits.
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await
    .expect("serve");
}
