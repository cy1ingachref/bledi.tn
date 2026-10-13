use chrono::{DateTime, Utc};
use uuid::Uuid;

use crate::geo::{Coordinates, UnlockRadius};
use crate::string_enum;

string_enum!(Visibility {
    Public => "public",
    Friends => "friends",
    Private => "private",
});

string_enum!(MediaType {
    Image => "image",
    Video => "video",
});

#[derive(Debug, Clone, PartialEq)]
pub struct Memory {
    pub id: Uuid,
    pub user_id: Uuid,
    pub lat: f64,
    pub lon: f64,
    pub title: Option<String>,
    pub description: Option<String>,
    pub media_url: String,
    pub media_type: MediaType,
    pub visibility: Visibility,
    pub unlock_radius_m: f64,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct TooFar {
    pub distance_m: f64,
}

#[derive(Debug, Clone, Default)]
pub struct MemoryChanges {
    pub title: Option<String>,
    pub description: Option<String>,
    pub visibility: Option<Visibility>,
    pub unlock_radius: Option<UnlockRadius>,
}

impl Memory {
    /// Whether `visible_to` needs to know if `viewer` is an accepted friend of the owner.
    pub fn needs_friendship_check(&self, viewer: Uuid) -> bool {
        self.visibility == Visibility::Friends && self.user_id != viewer
    }

    pub fn visible_to(&self, viewer: Uuid, accepted_friend: bool) -> bool {
        self.user_id == viewer
            || match self.visibility {
                Visibility::Public => true,
                Visibility::Friends => accepted_friend,
                Visibility::Private => false,
            }
    }

    /// The claimed position is client-supplied and can be spoofed: this limits casual
    /// long-range enumeration of media, it does not prove presence.
    pub fn unlock_from(&self, position: Coordinates) -> Result<f64, TooFar> {
        let distance_m = position.distance_m(self.lat, self.lon);
        if distance_m <= self.unlock_radius_m {
            Ok(distance_m)
        } else {
            Err(TooFar { distance_m })
        }
    }

    /// Absent fields keep their current value.
    pub fn apply(&mut self, changes: MemoryChanges, now: DateTime<Utc>) {
        if let Some(title) = changes.title {
            self.title = Some(title);
        }
        if let Some(description) = changes.description {
            self.description = Some(description);
        }
        if let Some(visibility) = changes.visibility {
            self.visibility = visibility;
        }
        if let Some(radius) = changes.unlock_radius {
            self.unlock_radius_m = radius.metres();
        }
        self.updated_at = now;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn memory(visibility: Visibility) -> Memory {
        Memory {
            id: Uuid::new_v4(),
            user_id: Uuid::new_v4(),
            lat: 36.8,
            lon: 10.18,
            title: Some("old".into()),
            description: None,
            media_url: "https://media.bledi.tn/x.jpg".into(),
            media_type: MediaType::Image,
            visibility,
            unlock_radius_m: 200.0,
            created_at: DateTime::UNIX_EPOCH,
            updated_at: DateTime::UNIX_EPOCH,
        }
    }

    #[test]
    fn the_owner_always_sees_their_memory() {
        for v in [Visibility::Public, Visibility::Friends, Visibility::Private] {
            let m = memory(v);
            assert!(m.visible_to(m.user_id, false));
            assert!(!m.needs_friendship_check(m.user_id));
        }
    }

    #[test]
    fn others_see_public_friends_only_when_friends_and_never_private() {
        let stranger = Uuid::new_v4();
        assert!(memory(Visibility::Public).visible_to(stranger, false));
        let friends_only = memory(Visibility::Friends);
        assert!(friends_only.needs_friendship_check(stranger));
        assert!(!friends_only.visible_to(stranger, false));
        assert!(friends_only.visible_to(stranger, true));
        assert!(!memory(Visibility::Private).visible_to(stranger, true));
    }

    #[test]
    fn unlock_inside_the_radius_returns_the_distance() {
        let m = memory(Visibility::Public);
        let on_pin = m.unlock_from(Coordinates::in_tunisia(36.8, 10.18).unwrap());
        assert!(on_pin.unwrap() < 1.0);
        let near = m.unlock_from(Coordinates::in_tunisia(36.8005, 10.18).unwrap());
        assert!(near.unwrap() > 0.0);
    }

    #[test]
    fn unlock_outside_the_radius_reports_how_far() {
        let m = memory(Visibility::Public);
        let far = m
            .unlock_from(Coordinates::in_tunisia(36.81, 10.18).unwrap())
            .unwrap_err();
        assert!((1000.0..1200.0).contains(&far.distance_m), "{far:?}");
    }

    #[test]
    fn apply_changes_only_what_is_given_and_stamps_the_update() {
        let mut m = memory(Visibility::Public);
        let now = Utc::now();
        m.apply(
            MemoryChanges {
                visibility: Some(Visibility::Private),
                unlock_radius: Some(UnlockRadius::new(500.0).unwrap()),
                ..MemoryChanges::default()
            },
            now,
        );
        assert_eq!(m.title.as_deref(), Some("old"));
        assert_eq!(m.visibility, Visibility::Private);
        assert_eq!(m.unlock_radius_m, 500.0);
        assert_eq!(m.updated_at, now);
    }

    #[test]
    fn enums_round_trip_through_their_text_form() {
        for v in [Visibility::Public, Visibility::Friends, Visibility::Private] {
            assert_eq!(Visibility::try_from(v.as_str().to_string()), Ok(v));
        }
        assert!(MediaType::try_from("gif".to_string()).is_err());
    }
}
