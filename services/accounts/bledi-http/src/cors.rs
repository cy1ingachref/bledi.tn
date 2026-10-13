use axum::http::{header, HeaderValue, Method};
use tower_http::cors::CorsLayer;

pub const DEFAULT_ALLOWED_ORIGINS: &[&str] = &[
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
];

/// Parses a comma-separated origin list. A bad entry is an error rather than skipped: an
/// origin that never matches fails closed, and the operator would never learn about the typo.
/// The shape check matters because a header value may legally contain spaces.
pub fn parse_allowed_origins(raw: &str) -> Result<Vec<HeaderValue>, String> {
    raw.split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|origin| {
            if origin == "*" {
                return Err("'*' is not allowed: list the origins explicitly".to_owned());
            }
            let host = origin
                .strip_prefix("https://")
                .or_else(|| origin.strip_prefix("http://"))
                .ok_or_else(|| format!("{origin:?} must start with http:// or https://"))?
                .split('/')
                .next()
                .unwrap_or_default();
            if host.is_empty() || host.contains(char::is_whitespace) {
                return Err(format!("{origin:?} has a malformed host"));
            }
            HeaderValue::from_str(origin).map_err(|_| format!("{origin:?} is not a header value"))
        })
        .collect()
}

/// Credentials stay off: the API takes a bearer token the browser never attaches on its own,
/// and leaving them off rules out the open wildcard-with-credentials policy by construction.
pub fn layer(allowed_origins: Vec<HeaderValue>) -> CorsLayer {
    CorsLayer::new()
        .allow_origin(allowed_origins)
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PUT,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers([header::AUTHORIZATION, header::CONTENT_TYPE])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_localhost_only() {
        let origins = parse_allowed_origins(&DEFAULT_ALLOWED_ORIGINS.join(",")).unwrap();
        assert_eq!(origins.len(), DEFAULT_ALLOWED_ORIGINS.len());
        for origin in origins {
            let origin = origin.to_str().unwrap();
            assert!(
                origin.starts_with("http://127.0.0.1:") || origin.starts_with("http://localhost:")
            );
        }
    }

    #[test]
    fn accepts_a_list_with_blanks() {
        let origins = parse_allowed_origins(" https://a.example , ,http://b.example/").unwrap();
        assert_eq!(origins.len(), 2);
    }

    #[test]
    fn rejects_wildcards_schemeless_and_malformed_origins() {
        for raw in [
            "*",
            "http://ok.example,*",
            "example.com",
            "localhost:5173",
            "not a url",
            "http://",
            "http://bad host",
        ] {
            assert!(
                parse_allowed_origins(raw).is_err(),
                "{raw:?} must be refused"
            );
        }
    }
}
