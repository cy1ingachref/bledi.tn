use axum::http::HeaderValue;
use bledi_http::cors::{parse_allowed_origins, DEFAULT_ALLOWED_ORIGINS};

/// HS256 is only as strong as its secret, and a short one falls to an offline brute force of
/// a single issued token.
pub const MIN_JWT_SECRET_BYTES: usize = 32;

/// Everything the server reads from its environment. There are deliberately no defaults for
/// the secret or the database: a default credential ends up shared by every deployment.
pub struct Config {
    pub database_url: String,
    pub jwt_secret: Vec<u8>,
    pub allowed_origins: Vec<HeaderValue>,
    pub trust_proxy_headers: bool,
}

impl Config {
    pub fn from_env() -> Result<Self, String> {
        Self::from_lookup(|name| std::env::var(name).ok())
    }

    fn from_lookup(var: impl Fn(&str) -> Option<String>) -> Result<Self, String> {
        let set = |name: &str| var(name).filter(|v| !v.trim().is_empty());

        let jwt_secret = set("JWT_SECRET").ok_or(
            "JWT_SECRET is not set. Set it to at least 32 random bytes (e.g. `openssl rand -hex 32`).",
        )?;
        let jwt_secret = jwt_secret.trim();
        if jwt_secret.len() < MIN_JWT_SECRET_BYTES {
            return Err(format!(
                "JWT_SECRET is too short ({} bytes). It must be at least {MIN_JWT_SECRET_BYTES} bytes of random data.",
                jwt_secret.len()
            ));
        }

        let database_url = set("DATABASE_URL")
            .ok_or("DATABASE_URL is not set. Set it to a PostgreSQL connection string.")?;

        let origins = set("ALLOWED_ORIGINS").unwrap_or_else(|| DEFAULT_ALLOWED_ORIGINS.join(","));
        let allowed_origins =
            parse_allowed_origins(&origins).map_err(|e| format!("ALLOWED_ORIGINS: {e}"))?;
        if allowed_origins.is_empty() {
            return Err("ALLOWED_ORIGINS lists no origin.".into());
        }

        let trust_proxy_headers =
            var("TRUST_PROXY_HEADERS").is_some_and(|v| v == "1" || v.eq_ignore_ascii_case("true"));

        Ok(Self {
            database_url,
            jwt_secret: jwt_secret.as_bytes().to_vec(),
            allowed_origins,
            trust_proxy_headers,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SECRET: &str = "0123456789abcdef0123456789abcdef";

    fn config(vars: &[(&str, &str)]) -> Result<Config, String> {
        Config::from_lookup(|name| {
            vars.iter()
                .find(|(key, _)| *key == name)
                .map(|(_, value)| value.to_string())
        })
    }

    #[test]
    fn the_secret_and_database_are_required() {
        assert!(config(&[("DATABASE_URL", "db")]).is_err());
        assert!(config(&[("JWT_SECRET", SECRET)]).is_err());
        let short = config(&[("JWT_SECRET", &SECRET[1..]), ("DATABASE_URL", "db")]);
        assert!(short.err().unwrap().contains("too short"));
    }

    fn with(name: &'static str, value: &'static str) -> Result<Config, String> {
        config(&[
            ("JWT_SECRET", SECRET),
            ("DATABASE_URL", "db"),
            (name, value),
        ])
    }

    #[test]
    fn defaults_to_the_local_origins_and_untrusted_proxies() {
        let config = with("UNRELATED", "").unwrap();
        assert_eq!(config.allowed_origins.len(), DEFAULT_ALLOWED_ORIGINS.len());
        assert!(!config.trust_proxy_headers);
        let trusted = with("TRUST_PROXY_HEADERS", "TRUE").unwrap();
        assert!(trusted.trust_proxy_headers);
    }

    #[test]
    fn a_bad_origin_stops_startup() {
        assert!(with("ALLOWED_ORIGINS", "https://ok.example,typo.example").is_err());
        assert!(with("ALLOWED_ORIGINS", ",").is_err());
        let config = with("ALLOWED_ORIGINS", "https://ok.example").unwrap();
        assert_eq!(config.allowed_origins.len(), 1);
    }
}
