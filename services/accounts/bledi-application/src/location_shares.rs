use std::sync::Arc;

use bledi_domain::geo::Coordinates;
use bledi_domain::location_share::{self, LocationShare};
use bledi_domain::text;
use chrono::{DateTime, Utc};
use serde::Deserialize;
use uuid::Uuid;

use crate::friendships::accepted_friend_ids;
use crate::ports::{Clock, FriendshipStore, LocationShareStore, NewLocationShare, Result};
use crate::{AppError, Missing, Nearby, Ports};

const NEARBY_LIMIT: usize = 100;

#[derive(Debug, Deserialize)]
pub struct ShareLocation {
    pub lat: f64,
    pub lon: f64,
    pub accuracy_m: Option<f64>,
    pub note: Option<String>,
    pub is_active: bool,
    pub expires_at: Option<DateTime<Utc>>,
}

#[derive(Clone)]
pub struct LocationShares {
    shares: Arc<dyn LocationShareStore>,
    friendships: Arc<dyn FriendshipStore>,
    clock: Arc<dyn Clock>,
}

impl LocationShares {
    pub fn new(ports: &Ports) -> Self {
        Self {
            shares: ports.location_shares.clone(),
            friendships: ports.friendships.clone(),
            clock: ports.clock.clone(),
        }
    }

    pub async fn mine(&self, me: Uuid) -> Result<Vec<LocationShare>> {
        self.shares.owned_by(me).await
    }

    /// Live shares of accepted friends only.
    pub async fn nearby(&self, me: Uuid, query: Nearby) -> Result<Vec<LocationShare>> {
        let area = query.area()?;
        let friends = accepted_friend_ids(self.friendships.as_ref(), me).await?;
        self.shares
            .nearby(&friends, &area, self.clock.now(), NEARBY_LIMIT)
            .await
    }

    pub async fn create(&self, me: Uuid, input: ShareLocation) -> Result<LocationShare> {
        let share = self.validate(me, input)?;
        self.shares.insert(share).await
    }

    pub async fn update(&self, me: Uuid, id: Uuid, input: ShareLocation) -> Result<LocationShare> {
        let mut share = self
            .shares
            .get(id)
            .await?
            .ok_or(AppError::NotFound(Missing::LocationShare))?;
        if share.user_id != me {
            return Err(AppError::Forbidden);
        }
        let new = self.validate(me, input)?;
        share.lat = new.location.lat();
        share.lon = new.location.lon();
        share.accuracy_m = new.accuracy_m;
        share.note = new.note;
        share.is_active = new.is_active;
        share.expires_at = Some(new.expires_at);
        share.updated_at = self.clock.now();
        self.shares.update(&share).await?;
        Ok(share)
    }

    pub async fn delete(&self, me: Uuid, id: Uuid) -> Result<()> {
        if self.shares.delete(id, me).await? {
            Ok(())
        } else {
            Err(AppError::NotFound(Missing::LocationShare))
        }
    }

    fn validate(&self, me: Uuid, input: ShareLocation) -> Result<NewLocationShare> {
        Ok(NewLocationShare {
            user_id: me,
            location: Coordinates::in_tunisia(input.lat, input.lon)?,
            accuracy_m: location_share::accuracy_m(input.accuracy_m)?,
            note: text::note(input.note.as_deref())?,
            is_active: input.is_active,
            expires_at: location_share::expiry(input.expires_at, self.clock.now())?,
        })
    }
}

#[cfg(test)]
mod tests {
    use chrono::Duration;

    use super::*;
    use crate::testing::Fakes;

    fn share(expires_in: Option<Duration>, now: DateTime<Utc>) -> ShareLocation {
        ShareLocation {
            lat: 36.8,
            lon: 10.2,
            accuracy_m: Some(10.0),
            note: Some("here".into()),
            is_active: true,
            expires_at: expires_in.map(|d| now + d),
        }
    }

    #[tokio::test]
    async fn a_share_must_expire_within_the_horizon() {
        let fakes = Fakes::new();
        let shares = LocationShares::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let now = fakes.now();
        for bad in [None, Some(Duration::hours(48)), Some(Duration::minutes(-1))] {
            let err = shares.create(me, share(bad, now)).await.unwrap_err();
            assert_eq!(err.code(), "invalid_expiry");
        }
        let created = shares
            .create(me, share(Some(Duration::hours(1)), now))
            .await
            .unwrap();
        assert_eq!(created.note.as_deref(), Some("here"));
        assert_eq!(shares.mine(me).await.unwrap(), vec![created]);
    }

    #[tokio::test]
    async fn friends_see_live_shares_nearby_and_strangers_do_not() {
        let fakes = Fakes::new();
        let shares = LocationShares::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let friend = fakes.user("friend@example.com").await;
        let stranger = fakes.user("stranger@example.com").await;
        fakes.befriend(me, friend).await;
        let now = fakes.now();
        shares
            .create(me, share(Some(Duration::hours(1)), now))
            .await
            .unwrap();
        let mut paused = share(Some(Duration::hours(1)), now);
        paused.is_active = false;
        shares.create(me, paused).await.unwrap();

        let here = Nearby {
            lat: 36.8,
            lon: 10.2,
            radius_m: Some(1000.0),
        };
        assert_eq!(shares.nearby(friend, here).await.unwrap().len(), 1);
        assert!(shares.nearby(stranger, here).await.unwrap().is_empty());
        assert!(shares.nearby(me, here).await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn only_the_owner_updates_a_share() {
        let fakes = Fakes::new();
        let shares = LocationShares::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let other = fakes.user("other@example.com").await;
        let now = fakes.now();
        let created = shares
            .create(me, share(Some(Duration::hours(1)), now))
            .await
            .unwrap();

        let err = shares
            .update(other, created.id, share(Some(Duration::hours(2)), now))
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::Forbidden));
        let moved = ShareLocation {
            lat: 36.9,
            ..share(Some(Duration::hours(2)), now)
        };
        let updated = shares.update(me, created.id, moved).await.unwrap();
        assert_eq!(updated.lat, 36.9);
        assert_eq!(updated.expires_at, Some(now + Duration::hours(2)));
        assert_eq!(shares.mine(me).await.unwrap(), vec![updated]);

        let err = shares.delete(other, created.id).await.unwrap_err();
        assert!(matches!(err, AppError::NotFound(Missing::LocationShare)));
        shares.delete(me, created.id).await.unwrap();
    }
}
