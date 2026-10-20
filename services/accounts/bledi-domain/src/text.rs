//! Text input rules. Over-long input is rejected, never truncated, so stored data is what the user sent.

use crate::{Invalid, ValidationError};

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
pub const MEDIA_KEY_MAX_CHARS: usize = 64;

type Result<T> = std::result::Result<T, ValidationError>;

fn fail<T>(kind: Invalid, message: impl Into<String>) -> Result<T> {
    Err(ValidationError::new(kind, message))
}

// Characters, not bytes: an Arabic password of 8 letters is 8 characters to its owner.
fn max_chars(value: &str, max: usize, field: &str, kind: Invalid) -> Result<()> {
    if value.chars().count() > max {
        return fail(kind, format!("{field} must be at most {max} characters"));
    }
    Ok(())
}

/// Trims and lowercases. Deliberately not an RFC 5322 parser: it rejects what is clearly wrong.
pub fn email(raw: &str) -> Result<String> {
    let value = raw.trim().to_lowercase();
    let bad = |message: &str| fail(Invalid::Email, message);
    if value.is_empty() {
        return bad("email is required");
    }
    max_chars(&value, EMAIL_MAX_CHARS, "email", Invalid::Email)?;
    if value.chars().any(char::is_whitespace) {
        return bad("email must not contain whitespace");
    }
    let Some((local, domain)) = value.split_once('@') else {
        return bad("email must contain exactly one '@'");
    };
    if domain.contains('@') {
        return bad("email must contain exactly one '@'");
    }
    if local.is_empty() {
        return bad("email local part must not be empty");
    }
    if domain.is_empty() {
        return bad("email domain must not be empty");
    }
    if !domain.contains('.') {
        return bad("email domain must contain a '.'");
    }
    if domain.starts_with('.') || domain.ends_with('.') || domain.contains("..") {
        return bad("email domain is malformed");
    }
    let tld = domain.rsplit('.').next().unwrap_or_default();
    if tld.len() < 2 || !tld.chars().all(|c| c.is_ascii_alphabetic()) {
        return bad("email top-level domain is malformed");
    }
    Ok(value)
}

pub fn password(raw: &str) -> Result<()> {
    let n = raw.chars().count();
    if n < PASSWORD_MIN_CHARS {
        return fail(
            Invalid::Password,
            format!("password must be at least {PASSWORD_MIN_CHARS} characters"),
        );
    }
    max_chars(raw, PASSWORD_MAX_CHARS, "password", Invalid::Password)
}

/// Blank becomes `None`.
pub fn display_name(value: Option<&str>) -> Result<Option<String>> {
    let Some(trimmed) = value.map(str::trim).filter(|v| !v.is_empty()) else {
        return Ok(None);
    };
    max_chars(
        trimmed,
        DISPLAY_NAME_MAX_CHARS,
        "display_name",
        Invalid::Text,
    )?;
    Ok(Some(trimmed.to_string()))
}

fn optional(value: Option<&str>, max: usize, field: &str) -> Result<Option<String>> {
    let Some(raw) = value else { return Ok(None) };
    max_chars(raw, max, field, Invalid::Text)?;
    Ok(Some(raw.to_string()))
}

pub fn title(value: Option<&str>) -> Result<Option<String>> {
    optional(value, TITLE_MAX_CHARS, "title")
}

pub fn description(value: Option<&str>) -> Result<Option<String>> {
    optional(value, DESCRIPTION_MAX_CHARS, "description")
}

pub fn note(value: Option<&str>) -> Result<Option<String>> {
    optional(value, NOTE_MAX_CHARS, "note")
}

pub fn label(value: Option<&str>) -> Result<Option<String>> {
    optional(value, LABEL_MAX_CHARS, "label")
}

pub fn ref_id(raw: &str) -> Result<String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return fail(Invalid::Text, "ref_id is required");
    }
    max_chars(trimmed, REF_ID_MAX_CHARS, "ref_id", Invalid::Text)?;
    Ok(trimmed.to_string())
}

/// Absolute http(s) URLs only; `data:` URLs would let a client store arbitrary content.
/// This does not make remote media safe (the viewer's browser still fetches it), see
/// docs/media-upload-design.md.
pub fn media_url(raw: &str) -> Result<String> {
    let trimmed = raw.trim();
    let bad = |message: &str| fail(Invalid::MediaUrl, message);
    if trimmed.is_empty() {
        return bad("media_url is required");
    }
    max_chars(trimmed, MEDIA_URL_MAX_CHARS, "media_url", Invalid::MediaUrl)?;
    let lower = trimmed.to_ascii_lowercase();
    if lower.starts_with("data:") {
        return bad("media_url must not be a data: URL");
    }
    if !(lower.starts_with("http://") || lower.starts_with("https://")) {
        return bad("media_url must be an absolute http:// or https:// URL");
    }
    let after_scheme = trimmed.split_once("://").map_or("", |(_, rest)| rest);
    let host = after_scheme
        .split(['/', '?', '#'])
        .next()
        .unwrap_or_default();
    if host.is_empty() {
        return bad("media_url is missing a host");
    }
    if host.contains(char::is_whitespace) {
        return bad("media_url host must not contain whitespace");
    }
    Ok(trimmed.to_string())
}

/// The key of a photo inside the media root. It is a file name, never a path: anything that
/// could escape the root is refused, so a key can be joined onto the root without escaping it.
pub fn media_key(raw: &str) -> Result<String> {
    let value = raw.trim();
    let bad = |message: &str| fail(Invalid::MediaKey, message);
    if value.is_empty() {
        return bad("media_key is required");
    }
    max_chars(value, MEDIA_KEY_MAX_CHARS, "media_key", Invalid::MediaKey)?;
    if value.starts_with('.') || value.contains("..") {
        return bad("media_key must not be a path");
    }
    if !value
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
    {
        return bad("media_key has characters that are not allowed");
    }
    Ok(value.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn email_normalises_and_validates() {
        assert_eq!(email("  User@Example.COM ").unwrap(), "user@example.com");
        for bad in [
            "",
            "no-at-sign",
            "two@at@example.com",
            "@example.com",
            "user@",
            "user@localhost",
            "user@example.c",
            "user@exa mple.com",
            "user@example..com",
            "@example..com",
        ] {
            assert_eq!(email(bad).unwrap_err().kind, Invalid::Email, "{bad:?}");
        }
        assert!(email(&format!("{}@example.com", "a".repeat(300))).is_err());
    }

    #[test]
    fn password_length_counts_characters_not_bytes() {
        assert!(password("1234567").is_err());
        assert!(password("12345678").is_ok());
        assert!(password(&"a".repeat(PASSWORD_MAX_CHARS)).is_ok());
        assert!(password(&"a".repeat(PASSWORD_MAX_CHARS + 1)).is_err());
        assert!(password("كلمةالسر").is_ok());
    }

    #[test]
    fn media_url_accepts_only_absolute_http_urls() {
        assert!(media_url("https://media.bledi.tn/a/b.jpg").is_ok());
        assert!(media_url("http://example.com/x.png").is_ok());
        for bad in [
            "data:image/png;base64,AAAA",
            "javascript:alert(1)",
            "ftp://example.com/x",
            "//example.com/x",
            "",
            "https://",
        ] {
            assert_eq!(
                media_url(bad).unwrap_err().kind,
                Invalid::MediaUrl,
                "{bad:?}"
            );
        }
        assert!(media_url(&format!("https://example.com/{}", "a".repeat(3000))).is_err());
    }

    #[test]
    fn media_key_is_a_file_name_not_a_path() {
        assert_eq!(media_key(" 3f1c1e2a-1.jpg ").unwrap(), "3f1c1e2a-1.jpg");
        for bad in [
            "",
            "../secret",
            "..",
            ".hidden",
            "dir/file.jpg",
            "dir\\file.jpg",
            "with space.jpg",
            "file.jpg?x=1",
        ] {
            assert_eq!(
                media_key(bad).unwrap_err().kind,
                Invalid::MediaKey,
                "{bad:?}"
            );
        }
        assert!(media_key(&"a".repeat(MEDIA_KEY_MAX_CHARS + 1)).is_err());
    }

    #[test]
    fn optional_text_rejects_rather_than_truncates() {
        assert_eq!(title(Some("ok")).unwrap().as_deref(), Some("ok"));
        assert_eq!(title(None).unwrap(), None);
        assert!(title(Some(&"x".repeat(TITLE_MAX_CHARS + 1))).is_err());
        assert!(description(Some(&"x".repeat(DESCRIPTION_MAX_CHARS + 1))).is_err());
        assert!(note(Some(&"x".repeat(NOTE_MAX_CHARS + 1))).is_err());
        assert!(label(Some(&"x".repeat(LABEL_MAX_CHARS + 1))).is_err());
    }

    #[test]
    fn display_name_is_trimmed_and_blank_becomes_none() {
        assert_eq!(display_name(Some("   ")).unwrap(), None);
        assert_eq!(
            display_name(Some("  Achref ")).unwrap().as_deref(),
            Some("Achref")
        );
        assert!(display_name(Some(&"x".repeat(DISPLAY_NAME_MAX_CHARS + 1))).is_err());
    }

    #[test]
    fn ref_id_is_required_and_trimmed() {
        assert_eq!(ref_id("  st_1 ").unwrap(), "st_1");
        assert!(ref_id("   ").is_err());
        assert!(ref_id(&"x".repeat(REF_ID_MAX_CHARS + 1)).is_err());
    }
}
