//! A fixed-window limiter held in process memory. N replicas give N times the allowance and a
//! restart clears every window; counters that must hold across replicas belong in a shared store.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use axum::http::HeaderMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Limit {
    pub max_hits: u32,
    pub window: Duration,
}

impl Limit {
    pub const fn new(max_hits: u32, window: Duration) -> Self {
        Self { max_hits, window }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct RateLimits {
    pub login: Limit,
    pub register: Limit,
    pub unlock: Limit,
}

impl Default for RateLimits {
    fn default() -> Self {
        Self {
            login: Limit::new(10, Duration::from_secs(60)),
            register: Limit::new(5, Duration::from_secs(300)),
            unlock: Limit::new(30, Duration::from_secs(60)),
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum Decision {
    Allow,
    Deny { retry_after_secs: u64 },
}

#[derive(Debug)]
struct Window {
    count: u32,
    started: Instant,
}

#[derive(Debug, Default)]
pub struct RateLimiter {
    windows: Mutex<HashMap<String, Window>>,
}

impl RateLimiter {
    pub fn check(&self, key: &str, limit: Limit) -> Decision {
        let now = Instant::now();
        // The counters are advisory: a panic elsewhere must not take the endpoints down with it.
        let mut windows = self.windows.lock().unwrap_or_else(|p| p.into_inner());
        windows.retain(|_, w| now.duration_since(w.started) < limit.window);

        let window = windows.entry(key.to_owned()).or_insert(Window {
            count: 0,
            started: now,
        });
        if window.count >= limit.max_hits {
            let remaining = limit
                .window
                .saturating_sub(now.duration_since(window.started));
            return Decision::Deny {
                retry_after_secs: remaining.as_secs().max(1),
            };
        }
        window.count += 1;
        Decision::Allow
    }

    #[cfg(test)]
    fn tracked_keys(&self) -> usize {
        self.windows.lock().map(|w| w.len()).unwrap_or(0)
    }
}

/// The key for per-IP limits. `X-Forwarded-For` is client controlled, so it counts only behind
/// a proxy that overwrites it; otherwise any caller could pick a fresh bucket per request.
/// Without a peer address every caller shares one bucket, which is stricter, not looser.
pub fn client_ip(headers: &HeaderMap, peer: Option<SocketAddr>, trust_proxy: bool) -> String {
    let forwarded = trust_proxy
        .then(|| headers.get("x-forwarded-for")?.to_str().ok())
        .flatten()
        .and_then(|v| v.split(',').next())
        .map(str::trim)
        .filter(|ip| !ip.is_empty());
    match (forwarded, peer) {
        (Some(ip), _) => ip.to_owned(),
        (None, Some(addr)) => addr.ip().to_string(),
        (None, None) => "unknown".to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limit(max_hits: u32, secs: u64) -> Limit {
        Limit::new(max_hits, Duration::from_secs(secs))
    }

    #[test]
    fn denies_past_the_limit_per_key() {
        let limiter = RateLimiter::default();
        for _ in 0..3 {
            assert_eq!(limiter.check("a", limit(3, 60)), Decision::Allow);
        }
        match limiter.check("a", limit(3, 60)) {
            Decision::Deny { retry_after_secs } => assert!((1..=60).contains(&retry_after_secs)),
            Decision::Allow => panic!("the fourth hit must be denied"),
        }
        assert_eq!(limiter.check("b", limit(3, 60)), Decision::Allow);
    }

    #[test]
    fn expired_windows_reset_and_are_pruned() {
        let limiter = RateLimiter::default();
        assert_eq!(limiter.check("k", limit(1, 0)), Decision::Allow);
        assert_eq!(limiter.check("k", limit(1, 0)), Decision::Allow);

        assert_eq!(limiter.check("old", limit(5, 3600)), Decision::Allow);
        assert_eq!(limiter.check("new", limit(5, 0)), Decision::Allow);
        assert_eq!(limiter.tracked_keys(), 1);
    }

    #[test]
    fn defaults_match_the_documented_limits() {
        let limits = RateLimits::default();
        assert_eq!(limits.login, limit(10, 60));
        assert_eq!(limits.register, limit(5, 300));
        assert_eq!(limits.unlock, limit(30, 60));
    }

    #[test]
    fn forwarded_for_counts_only_when_trusted() {
        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", "203.0.113.7, 10.0.0.1".parse().unwrap());
        let peer = Some(SocketAddr::from(([10, 0, 0, 1], 4000)));
        assert_eq!(client_ip(&headers, peer, true), "203.0.113.7");
        assert_eq!(client_ip(&headers, peer, false), "10.0.0.1");
        assert_eq!(client_ip(&HeaderMap::new(), None, true), "unknown");
    }
}
