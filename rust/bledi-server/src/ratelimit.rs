//! A small in-process fixed-window rate limiter.
//!
//! Deliberately dependency-free and in-memory. This is adequate for a single
//! instance and it is honest about its limits: state is per-process, so N
//! replicas give N times the allowance, and a restart clears every window. If
//! this ever needs to hold across replicas, move the counters to Redis — do not
//! pretend the in-process map does that.
//!
//! Used for:
//!   * login / register, keyed by client IP (see [`crate::handlers::client_ip`])
//!   * memory unlock, keyed by authenticated user id

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// A limit: at most `max_hits` in any `window`.
#[derive(Debug, Clone, Copy)]
pub struct Limit {
    pub max_hits: u32,
    pub window: Duration,
}

impl Limit {
    pub const fn new(max_hits: u32, window: Duration) -> Self {
        Self { max_hits, window }
    }
}

pub const LOGIN: Limit = Limit::new(10, Duration::from_secs(60));
pub const REGISTER: Limit = Limit::new(5, Duration::from_secs(300));
pub const UNLOCK: Limit = Limit::new(30, Duration::from_secs(60));

/// The limits an instance runs with.
///
/// These are configuration rather than constants baked into the handlers for a
/// practical reason: the integration tests drive many registrations from a
/// single loopback address in parallel, which trips the production register
/// limit and produces 429s that look like unrelated failures. Tests inject
/// generous limits via [`RateLimits::for_tests`] instead of the limiter being
/// disabled, so the code path is still exercised.
#[derive(Debug, Clone, Copy)]
pub struct RateLimits {
    pub login: Limit,
    pub register: Limit,
    pub unlock: Limit,
}

impl Default for RateLimits {
    fn default() -> Self {
        Self {
            login: LOGIN,
            register: REGISTER,
            unlock: UNLOCK,
        }
    }
}

impl RateLimits {
    /// Wide limits for integration tests that share one loopback IP.
    ///
    /// The limiter's own behaviour is covered by unit tests in this module, so
    /// relaxing it here does not leave it untested.
    pub fn for_tests() -> Self {
        Self {
            login: Limit::new(100_000, Duration::from_secs(1)),
            register: Limit::new(100_000, Duration::from_secs(1)),
            unlock: Limit::new(100_000, Duration::from_secs(1)),
        }
    }
}

#[derive(Debug)]
struct Window {
    count: u32,
    started: Instant,
}

/// Outcome of a rate-limit check.
#[derive(Debug, PartialEq, Eq)]
pub enum Decision {
    Allow,
    Deny { retry_after_secs: u64 },
}

#[derive(Debug, Default)]
pub struct RateLimiter {
    windows: Mutex<HashMap<String, Window>>,
}

impl RateLimiter {
    pub fn new() -> Self {
        Self {
            windows: Mutex::new(HashMap::new()),
        }
    }

    /// Record an attempt by `key` and decide whether it is allowed.
    pub fn check(&self, key: &str, limit: Limit) -> Decision {
        let now = Instant::now();
        let mut map = match self.windows.lock() {
            Ok(guard) => guard,
            // A poisoned lock means another thread panicked mid-update. The
            // counters are advisory, so recovering the data is better than
            // taking down the whole endpoint.
            Err(poisoned) => poisoned.into_inner(),
        };

        // Prune expired windows so the map cannot grow without bound as IPs and
        // users come and go. This runs on every check, which keeps it O(entries)
        // with a cheap comparison per entry.
        map.retain(|_, w| now.duration_since(w.started) < limit.window);

        let entry = map.entry(key.to_string()).or_insert_with(|| Window {
            count: 0,
            started: now,
        });

        if now.duration_since(entry.started) >= limit.window {
            entry.count = 0;
            entry.started = now;
        }

        if entry.count >= limit.max_hits {
            let elapsed = now.duration_since(entry.started);
            let remaining = limit.window.saturating_sub(elapsed);
            return Decision::Deny {
                retry_after_secs: remaining.as_secs().max(1),
            };
        }

        entry.count += 1;
        Decision::Allow
    }

    /// Number of tracked keys. Used by tests to assert pruning happens.
    #[cfg(test)]
    pub fn tracked_keys(&self) -> usize {
        self.windows.lock().map(|m| m.len()).unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limit(n: u32, secs: u64) -> Limit {
        Limit::new(n, Duration::from_secs(secs))
    }

    #[test]
    fn allows_up_to_the_limit_then_denies() {
        let rl = RateLimiter::new();
        let l = limit(3, 60);
        for i in 0..3 {
            assert_eq!(rl.check("a", l), Decision::Allow, "attempt {i} should pass");
        }
        match rl.check("a", l) {
            Decision::Deny { retry_after_secs } => assert!(retry_after_secs >= 1),
            Decision::Allow => panic!("4th attempt should have been denied"),
        }
    }

    #[test]
    fn keys_are_independent() {
        let rl = RateLimiter::new();
        let l = limit(1, 60);
        assert_eq!(rl.check("ip-1", l), Decision::Allow);
        // The window has just started, so the retry hint is the full window
        // minus the microseconds already elapsed. Assert the shape, not an
        // exact second.
        match rl.check("ip-1", l) {
            Decision::Deny { retry_after_secs } => {
                assert!(
                    (1..=60).contains(&retry_after_secs),
                    "got {retry_after_secs}"
                )
            }
            Decision::Allow => panic!("second attempt should have been denied"),
        }
        // A different key is unaffected.
        assert_eq!(rl.check("ip-2", l), Decision::Allow);
    }

    #[test]
    fn window_resets_after_it_expires() {
        let rl = RateLimiter::new();
        let l = limit(1, 0); // zero-length window: always expired
        assert_eq!(rl.check("k", l), Decision::Allow);
        assert_eq!(rl.check("k", l), Decision::Allow);
    }

    #[test]
    fn stale_keys_are_pruned() {
        let rl = RateLimiter::new();
        // A long window tracks the key...
        assert_eq!(rl.check("old", limit(5, 3600)), Decision::Allow);
        assert_eq!(rl.tracked_keys(), 1);
        // ...then a zero-window check prunes everything whose window lapsed.
        assert_eq!(rl.check("new", limit(5, 0)), Decision::Allow);
        assert_eq!(
            rl.tracked_keys(),
            1,
            "the stale key should have been pruned"
        );
    }

    #[test]
    fn login_and_register_limits_are_sane() {
        assert_eq!(LOGIN.max_hits, 10);
        assert_eq!(LOGIN.window, Duration::from_secs(60));
        assert_eq!(REGISTER.max_hits, 5);
        assert_eq!(REGISTER.window, Duration::from_secs(300));
        assert_eq!(UNLOCK.max_hits, 30);
    }
}
