use bledi_server::auth::secret_from_env;
use bledi_server::router;
use bledi_server::state::AppState;
use sqlx::postgres::PgPoolOptions;
use std::net::SocketAddr;
use tracing_subscriber::fmt;

#[tokio::main]
async fn main() {
    fmt().with_target(false).with_level(true).init();

    // Load .env if present, so `JWT_SECRET` and `DATABASE_URL` can live there
    // during development. Absent is fine — real deployments set them directly.
    let _ = dotenvy::dotenv();

    // Both of these are REQUIRED. There is no fallback: a default connection
    // string or a default signing key is how a service ends up publicly
    // reachable with credentials everybody knows.
    let jwt_secret = match secret_from_env() {
        Ok(secret) => secret,
        Err(reason) => {
            eprintln!("FATAL: refusing to start: {reason}");
            std::process::exit(1);
        }
    };

    let database_url = match std::env::var("DATABASE_URL") {
        Ok(url) if !url.trim().is_empty() => url,
        _ => {
            eprintln!(
                "FATAL: refusing to start: DATABASE_URL is not set. \
                 Set it to a PostgreSQL connection string."
            );
            std::process::exit(1);
        }
    };

    let allowed_origins = bledi_server::allowed_origins_from_env();
    if allowed_origins.is_empty() {
        eprintln!("FATAL: refusing to start: ALLOWED_ORIGINS resolved to an empty list.");
        std::process::exit(1);
    }

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await
        .expect("Failed to create pool");

    sqlx::migrate!()
        .run(&pool)
        .await
        .expect("Failed to run migrations");

    let state = AppState::new(pool, jwt_secret, allowed_origins);
    let app = router(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], 3000));
    tracing::info!("bledi-server listening on {}", addr);
    tracing::info!(
        "CORS origins: {} configured",
        bledi_server::DEFAULT_ALLOWED_ORIGINS.len()
    );

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    // `into_make_service_with_connect_info` exposes the peer SocketAddr to the
    // handlers, which is how the login/register rate limiter keys its buckets.
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .await
    .unwrap();
}
