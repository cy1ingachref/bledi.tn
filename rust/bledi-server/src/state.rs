use crate::ratelimit::RateLimiter;
use sqlx::PgPool;
use std::sync::Arc;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    /// HS256 signing/verification key, loaded from `JWT_SECRET` at startup.
    /// Never a compiled-in default — see `auth::secret_from_env`.
    pub jwt_secret: Arc<[u8]>,
    /// Allowed CORS origins, parsed from `ALLOWED_ORIGINS`.
    pub allowed_origins: Arc<Vec<axum::http::HeaderValue>>,
    /// Shared counters for login / register / unlock.
    pub rate_limiter: Arc<RateLimiter>,
}

impl AppState {
    pub fn new(
        pool: PgPool,
        jwt_secret: Vec<u8>,
        allowed_origins: Vec<axum::http::HeaderValue>,
    ) -> Self {
        Self {
            pool,
            jwt_secret: Arc::from(jwt_secret),
            allowed_origins: Arc::new(allowed_origins),
            rate_limiter: Arc::new(RateLimiter::new()),
        }
    }
}
