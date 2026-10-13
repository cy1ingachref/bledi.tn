//! Input validation for the HTTP layer.
//!
//! Every handler that accepts user input validates it here before touching the
//! database. The rules live in one place so a new endpoint cannot quietly skip
//! them, and so the bounds are greppable.
//!
//! Two deliberate choices worth knowing about:
//!
//! * **Non-finite floats are rejected explicitly.** `f64::NAN` compares false
//!   against every bound, so a naive `if !(min..=max).contains(&x)` is *not*
//!   enough on its own — `NAN < min` is false and `NAN > max` is false, so a
//!   range check written as a pair of comparisons lets NaN through. Every
//!   float rule below starts with `is_finite()`.
//! * **Nothing is silently truncated.** An over-long string is a 400, not a
//!   shortened string, because silent truncation corrupts user data in a way
//!   the client never learns about.
//!
//! ## Media upload — intended design (NOT implemented)
//!
//! There is no upload pipeline yet. `media_url` is validated as an absolute
//! http(s) URL, but that is only a mitigation: a valid https URL pointing at an
//! attacker's host still logs every viewer's IP, because the frontend renders
//! `<img src={media_url}>` directly.
//!
//! The intended fix, in order:
//!
//! 1. Object storage (S3-compatible: Cloudflare R2 in production, MinIO in
//!    dev) with a per-user key prefix.
//! 2. A `POST /api/v1/uploads` endpoint that returns a **presigned POST policy**
//!    carrying `content-length-range` and a content-type allowlist. A presigned
//!    PUT alone does not cap size; the policy form does.
//! 3. Server-side verification on create: the object exists, its real size is
//!    within the limit, and its magic number matches the declared type. Never
//!    trust the client's `Content-Type` or its declared `size_bytes`.
//! 4. Re-encode images and **strip all EXIF**, including GPS tags. This is a
//!    correctness requirement, not a nicety: an EXIF GPS tag would defeat
//!    `unlock_radius_m` entirely by publishing the exact pinned location.
//! 5. Store `media_key` (the object key), not an absolute URL, and sign on
//!    read. Serve from a single first-party host so `src` is never
//!    attacker-controlled.
//!
//! See `docs/media-upload-design.md` for the full specification.

/// Tunisia bounding box. A coordinate outside this is not a typo we should
/// accept — it is a client bug or an attack, and either way it must not reach
/// the geo queries.
pub const LAT_MIN: f64 = 30.0;
pub const LAT_MAX: f64 = 37.5;
pub const LON_MIN: f64 = 7.5;
pub const LON_MAX: f64 = 12.0;

/// `unlock_radius_m` bounds. The README promises a configurable 50–1000 m, so a
/// value outside that is rejected rather than clamped.
pub const UNLOCK_RADIUS_MIN_M: f64 = 50.0;
pub const UNLOCK_RADIUS_MAX_M: f64 = 1000.0;

/// Caps for client-supplied search radii.
///
/// These are caps, not clamps: a request above the cap is a 400. Silently
/// clamping would return a different answer than the caller asked for without
/// telling them, which is how a client ends up believing a 500 km search
/// succeeded when it only covered 5 km.
pub const NEARBY_RADIUS_MAX_M: f64 = 5_000.0;
pub const STATION_RADIUS_MAX_M: f64 = 50_000.0;

pub const PASSWORD_MIN_CHARS: usize = 8;
pub const PASSWORD_MAX_CHARS: usize = 128;
pub const EMAIL_MAX_CHARS: usize = 254;
pub const DISPLAY_NAME_MAX_CHARS: usize = 64;
pub const TITLE_MAX_CHARS: usize = 200;
pub const DESCRIPTION_MAX_CHARS: usize = 2000;
pub const NOTE_MAX_CHARS: usize = 500;
pub const REF_ID_MAX_CHARS: usize = 128;
pub const LABEL_MAX_CHARS: usize = 200;
pub const MEDIA_URL_MAX_CHARS: usize = 2048;

/// Location shares expire. The README says so, and an indefinite share is a
/// silent privacy leak: the user believes it lapses and it does not.
pub const SHARE_MAX_HORIZON_HOURS: i64 = 24;

/// A validation failure. Rendered as HTTP 400 with a specific message so the
/// client can tell the user which field is wrong.
#[derive(Debug)]
pub struct ValidationError(pub String);

impl std::fmt::Display for ValidationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for ValidationError {}

type VResult<T> = Result<T, ValidationError>;

fn fail<T>(msg: impl Into<String>) -> VResult<T> {
    Err(ValidationError(msg.into()))
}

// ── Floats ──────────────────────────────────────────────────────────────────

/// Check a float is finite and inside `[min, max]`.
///
/// `is_finite` first: NaN and ±Inf would otherwise slip past the comparisons.
fn finite_in_range(value: f64, min: f64, max: f64, field: &str) -> VResult<f64> {
    if !value.is_finite() {
        return fail(format!("{field} must be a finite number"));
    }
    if value < min || value > max {
        return fail(format!("{field} must be between {min} and {max}"));
    }
    Ok(value)
}

pub fn latitude(value: f64) -> VResult<f64> {
    finite_in_range(value, LAT_MIN, LAT_MAX, "lat")
}

pub fn longitude(value: f64) -> VResult<f64> {
    finite_in_range(value, LON_MIN, LON_MAX, "lon")
}

pub fn lat_lon(lat: f64, lon: f64) -> VResult<(f64, f64)> {
    Ok((latitude(lat)?, longitude(lon)?))
}

pub fn unlock_radius_m(value: f64) -> VResult<f64> {
    finite_in_range(
        value,
        UNLOCK_RADIUS_MIN_M,
        UNLOCK_RADIUS_MAX_M,
        "unlock_radius_m",
    )
}

/// A client-supplied search radius. `default` is used when absent.
pub fn search_radius_m(value: Option<f64>, max: f64, field: &str) -> VResult<f64> {
    match value {
        None => Ok(max.min(NEARBY_RADIUS_MAX_M)),
        Some(v) => {
            if !v.is_finite() {
                return fail(format!("{field} must be a finite number"));
            }
            if v <= 0.0 {
                return fail(format!("{field} must be greater than 0"));
            }
            if v > max {
                return fail(format!("{field} must be <= {max}"));
            }
            Ok(v)
        }
    }
}

pub fn accuracy_m(value: Option<f64>) -> VResult<Option<f64>> {
    match value {
        None => Ok(None),
        Some(v) => Ok(Some(finite_in_range(v, 0.0, 100_000.0, "accuracy_m")?)),
    }
}

// ── Strings ─────────────────────────────────────────────────────────────────

fn max_chars(value: &str, max: usize, field: &str) -> VResult<()> {
    // Count characters, not bytes: a 128-character Arabic password is 128
    // characters to the user even though it is far more than 128 bytes.
    let n = value.chars().count();
    if n > max {
        return fail(format!("{field} must be at most {max} characters"));
    }
    Ok(())
}

/// Trim, lowercase and validate an email address.
///
/// Deliberately not a full RFC 5322 parser — that is a famously bad idea. This
/// rejects what is clearly wrong and normalises what it accepts.
pub fn email(raw: &str) -> VResult<String> {
    let value = raw.trim().to_lowercase();
    if value.is_empty() {
        return fail("email is required");
    }
    max_chars(&value, EMAIL_MAX_CHARS, "email")?;
    if value.chars().any(char::is_whitespace) {
        return fail("email must not contain whitespace");
    }
    let parts: Vec<&str> = value.split('@').collect();
    if parts.len() != 2 {
        return fail("email must contain exactly one '@'");
    }
    let (local, domain) = (parts[0], parts[1]);
    if local.is_empty() {
        return fail("email local part must not be empty");
    }
    if domain.is_empty() {
        return fail("email domain must not be empty");
    }
    if !domain.contains('.') {
        return fail("email domain must contain a '.'");
    }
    if domain.starts_with('.') || domain.ends_with('.') || domain.contains("..") {
        return fail("email domain is malformed");
    }
    let tld = domain.rsplit('.').next().unwrap_or("");
    if tld.len() < 2 || !tld.chars().all(|c| c.is_ascii_alphabetic()) {
        return fail("email top-level domain is malformed");
    }
    Ok(value)
}

pub fn password(raw: &str) -> VResult<()> {
    let n = raw.chars().count();
    if n < PASSWORD_MIN_CHARS {
        return fail(format!(
            "password must be at least {PASSWORD_MIN_CHARS} characters"
        ));
    }
    if n > PASSWORD_MAX_CHARS {
        return fail(format!(
            "password must be at most {PASSWORD_MAX_CHARS} characters"
        ));
    }
    Ok(())
}

pub fn display_name(value: Option<&str>) -> VResult<Option<String>> {
    let Some(raw) = value else { return Ok(None) };
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }
    max_chars(trimmed, DISPLAY_NAME_MAX_CHARS, "display_name")?;
    Ok(Some(trimmed.to_string()))
}

pub fn title(value: Option<&str>) -> VResult<Option<String>> {
    optional_text(value, TITLE_MAX_CHARS, "title")
}

pub fn description(value: Option<&str>) -> VResult<Option<String>> {
    optional_text(value, DESCRIPTION_MAX_CHARS, "description")
}

pub fn note(value: Option<&str>) -> VResult<Option<String>> {
    optional_text(value, NOTE_MAX_CHARS, "note")
}

fn optional_text(value: Option<&str>, max: usize, field: &str) -> VResult<Option<String>> {
    let Some(raw) = value else { return Ok(None) };
    max_chars(raw, max, field)?;
    Ok(Some(raw.to_string()))
}

pub fn ref_id(raw: &str) -> VResult<String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return fail("ref_id is required");
    }
    max_chars(trimmed, REF_ID_MAX_CHARS, "ref_id")?;
    Ok(trimmed.to_string())
}

pub fn label(value: Option<&str>) -> VResult<Option<String>> {
    optional_text(value, LABEL_MAX_CHARS, "label")
}

/// Validate a media URL.
///
/// Only absolute `http`/`https` URLs are accepted. `data:` URLs are rejected
/// outright: they let a client embed arbitrary content in the database and
/// bypass the (future) upload pipeline entirely.
///
/// This does NOT make remote media safe — see the module doc comment. It only
/// stops the obviously-invalid cases from being stored.
pub fn media_url(raw: &str) -> VResult<String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return fail("media_url is required");
    }
    max_chars(trimmed, MEDIA_URL_MAX_CHARS, "media_url")?;
    let lower = trimmed.to_ascii_lowercase();
    if lower.starts_with("data:") {
        return fail("media_url must not be a data: URL");
    }
    if !(lower.starts_with("http://") || lower.starts_with("https://")) {
        return fail("media_url must be an absolute http:// or https:// URL");
    }
    // Require something that looks like a host after the scheme.
    let after_scheme = &trimmed[trimmed.find("://").map(|i| i + 3).unwrap_or(trimmed.len())..];
    let host = after_scheme
        .split(['/', '?', '#'])
        .next()
        .unwrap_or_default();
    if host.is_empty() {
        return fail("media_url is missing a host");
    }
    if host.contains(char::is_whitespace) {
        return fail("media_url host must not contain whitespace");
    }
    Ok(trimmed.to_string())
}

// ── Time ────────────────────────────────────────────────────────────────────

/// Validate a location share's expiry.
///
/// Required, in the future, and within [`SHARE_MAX_HORIZON_HOURS`]. The README
/// promises shares expire, and the schema allowed `NULL`, so a share could
/// previously be created that never lapsed.
pub fn share_expiry(
    expires_at: Option<chrono::DateTime<chrono::Utc>>,
) -> VResult<chrono::DateTime<chrono::Utc>> {
    let Some(expires_at) = expires_at else {
        return fail("expires_at is required");
    };
    let now = chrono::Utc::now();
    if expires_at <= now {
        return fail("expires_at must be in the future");
    }
    let horizon = chrono::Duration::hours(SHARE_MAX_HORIZON_HOURS);
    if expires_at > now + horizon {
        return fail(format!(
            "expires_at must be within {SHARE_MAX_HORIZON_HOURS} hours"
        ));
    }
    Ok(expires_at)
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{Duration, Utc};

    #[test]
    fn nan_latitude_is_rejected() {
        // The reason the range check is not a pair of comparisons.
        assert!(latitude(f64::NAN).is_err());
        assert!(latitude(f64::INFINITY).is_err());
        assert!(latitude(f64::NEG_INFINITY).is_err());
    }

    #[test]
    fn latitude_bounds() {
        assert!(latitude(36.8).is_ok());
        assert!(latitude(LAT_MIN).is_ok());
        assert!(latitude(LAT_MAX).is_ok());
        assert!(latitude(LAT_MIN - 0.1).is_err());
        assert!(latitude(48.85).is_err()); // Paris
    }

    #[test]
    fn longitude_bounds() {
        assert!(longitude(10.18).is_ok());
        assert!(longitude(LON_MIN - 0.1).is_err());
        assert!(longitude(2.35).is_err()); // Paris
    }

    #[test]
    fn unlock_radius_is_bounded_and_not_clamped() {
        assert!(unlock_radius_m(200.0).is_ok());
        assert!(unlock_radius_m(50.0).is_ok());
        assert!(unlock_radius_m(1000.0).is_ok());
        // A negative or huge radius is an error, not a silently-fixed value.
        assert!(unlock_radius_m(-1.0).is_err());
        assert!(unlock_radius_m(0.0).is_err());
        assert!(unlock_radius_m(1e9).is_err());
        assert!(unlock_radius_m(f64::NAN).is_err());
    }

    #[test]
    fn search_radius_caps_rather_than_clamps() {
        assert_eq!(
            search_radius_m(Some(1000.0), NEARBY_RADIUS_MAX_M, "radius_m").unwrap(),
            1000.0
        );
        // Above the cap is an error.
        assert!(search_radius_m(Some(999_999.0), NEARBY_RADIUS_MAX_M, "radius_m").is_err());
        assert!(search_radius_m(Some(-5.0), NEARBY_RADIUS_MAX_M, "radius_m").is_err());
        assert!(search_radius_m(Some(f64::NAN), NEARBY_RADIUS_MAX_M, "radius_m").is_err());
        // Absent falls back to the cap.
        assert_eq!(
            search_radius_m(None, NEARBY_RADIUS_MAX_M, "radius_m").unwrap(),
            NEARBY_RADIUS_MAX_M
        );
    }

    #[test]
    fn email_normalises_and_validates() {
        assert_eq!(email("  User@Example.COM ").unwrap(), "user@example.com");
        assert!(email("").is_err());
        assert!(email("no-at-sign").is_err());
        assert!(email("two@at@signs.com").is_err());
        assert!(email("@example.com").is_err());
        assert!(email("user@").is_err());
        assert!(email("user@localhost").is_err()); // no dot
        assert!(email("user@example.c").is_err()); // 1-char TLD
        assert!(email("user@exa mple.com").is_err()); // whitespace
        assert!(email("user@example..com").is_err());
        assert!(email(&format!("{}@example.com", "a".repeat(300))).is_err());
    }

    #[test]
    fn password_length_in_characters_not_bytes() {
        assert!(password("1234567").is_err()); // 7
        assert!(password("12345678").is_ok()); // 8
        assert!(password(&"a".repeat(128)).is_ok());
        assert!(password(&"a".repeat(129)).is_err());
        // 8 multi-byte characters are 8 characters, even though 16+ bytes.
        let arabic = "كلمةالسر"; // 8 chars
        assert_eq!(arabic.chars().count(), 8);
        assert!(password(arabic).is_ok());
    }

    #[test]
    fn media_url_rules() {
        assert!(media_url("https://media.bledi.tn/a/b.jpg").is_ok());
        assert!(media_url("http://example.com/x.png").is_ok());
        assert!(media_url("data:image/png;base64,AAAA").is_err());
        assert!(media_url("javascript:alert(1)").is_err());
        assert!(media_url("ftp://example.com/x").is_err());
        assert!(media_url("//example.com/x").is_err());
        assert!(media_url("").is_err());
        assert!(media_url("https://").is_err());
        assert!(media_url(&format!("https://example.com/{}", "a".repeat(3000))).is_err());
    }

    #[test]
    fn optional_text_rejects_rather_than_truncates() {
        assert!(title(Some("ok")).unwrap().is_some());
        assert!(title(None).unwrap().is_none());
        assert!(title(Some(&"x".repeat(TITLE_MAX_CHARS + 1))).is_err());
        assert!(description(Some(&"x".repeat(DESCRIPTION_MAX_CHARS + 1))).is_err());
        assert!(note(Some(&"x".repeat(NOTE_MAX_CHARS + 1))).is_err());
    }

    #[test]
    fn display_name_blank_becomes_none() {
        assert_eq!(display_name(Some("   ")).unwrap(), None);
        assert_eq!(
            display_name(Some("  Achref ")).unwrap().as_deref(),
            Some("Achref")
        );
        assert!(display_name(Some(&"x".repeat(DISPLAY_NAME_MAX_CHARS + 1))).is_err());
    }

    #[test]
    fn share_expiry_is_required_future_and_bounded() {
        assert!(share_expiry(None).is_err());
        assert!(share_expiry(Some(Utc::now() - Duration::minutes(1))).is_err());
        assert!(share_expiry(Some(Utc::now() + Duration::hours(1))).is_ok());
        assert!(share_expiry(Some(Utc::now() + Duration::hours(25))).is_err());
    }
}
