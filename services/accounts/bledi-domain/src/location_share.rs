use chrono::{DateTime, Duration, Utc};
use serde::Serialize;
use uuid::Uuid;

use crate::geo::finite_in_range;
use crate::{Invalid, ValidationError};

/// Shares always lapse: an open-ended share is a privacy leak the user does not expect.
pub const SHARE_MAX_HORIZON_HOURS: i64 = 24;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct LocationShare {
    pub id: Uuid,
    pub user_id: Uuid,
    pub lat: f64,
    pub lon: f64,
    pub accuracy_m: Option<f64>,
    pub note: Option<String>,
    pub is_active: bool,
    pub expires_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl LocationShare {
    pub fn is_live(&self, now: DateTime<Utc>) -> bool {
        self.is_active && self.expires_at.is_none_or(|at| at > now)
    }
}

pub fn expiry(
    expires_at: Option<DateTime<Utc>>,
    now: DateTime<Utc>,
) -> Result<DateTime<Utc>, ValidationError> {
    let Some(expires_at) = expires_at else {
        return Err(ValidationError::new(
            Invalid::Expiry,
            "expires_at is required",
        ));
    };
    if expires_at <= now {
        return Err(ValidationError::new(
            Invalid::Expiry,
            "expires_at must be in the future",
        ));
    }
    if expires_at > now + Duration::hours(SHARE_MAX_HORIZON_HOURS) {
        return Err(ValidationError::new(
            Invalid::Expiry,
            format!("expires_at must be within {SHARE_MAX_HORIZON_HOURS} hours"),
        ));
    }
    Ok(expires_at)
}

pub fn accuracy_m(value: Option<f64>) -> Result<Option<f64>, ValidationError> {
    value
        .map(|v| finite_in_range(v, 0.0, 100_000.0, "accuracy_m", Invalid::Accuracy))
        .transpose()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn expiry_is_required_in_the_future_and_within_the_horizon() {
        let now = Utc::now();
        assert!(expiry(None, now).is_err());
        assert!(expiry(Some(now), now).is_err());
        assert!(expiry(Some(now - Duration::minutes(1)), now).is_err());
        assert!(expiry(Some(now + Duration::hours(1)), now).is_ok());
        assert!(expiry(Some(now + Duration::hours(SHARE_MAX_HORIZON_HOURS)), now).is_ok());
        let too_far = expiry(Some(now + Duration::hours(25)), now).unwrap_err();
        assert_eq!(too_far.kind, Invalid::Expiry);
    }

    #[test]
    fn accuracy_is_optional_but_bounded() {
        assert_eq!(accuracy_m(None), Ok(None));
        assert_eq!(accuracy_m(Some(10.0)), Ok(Some(10.0)));
        assert!(accuracy_m(Some(-1.0)).is_err());
        assert!(accuracy_m(Some(f64::NAN)).is_err());
    }

    #[test]
    fn a_share_is_live_while_active_and_unexpired() {
        let now = Utc::now();
        let mut share = LocationShare {
            id: Uuid::new_v4(),
            user_id: Uuid::new_v4(),
            lat: 36.8,
            lon: 10.2,
            accuracy_m: None,
            note: None,
            is_active: true,
            expires_at: Some(now + Duration::hours(1)),
            created_at: now,
            updated_at: now,
        };
        assert!(share.is_live(now));
        assert!(!share.is_live(now + Duration::hours(2)));
        share.is_active = false;
        assert!(!share.is_live(now));
    }
}
