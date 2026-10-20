use std::sync::Arc;

use bledi_domain::friendship;
use bledi_domain::geo::{Coordinates, UnlockRadius};
use bledi_domain::memory::{MediaType, Memory, MemoryChanges, Visibility};
use bledi_domain::text;
use serde::Deserialize;
use uuid::Uuid;

use crate::friendships::accepted_friend_ids;
use crate::ports::{Clock, FriendshipStore, MemoryStore, NewMemory, Result};
use crate::{AppError, Missing, Nearby, Ports, Position};

const NEARBY_LIMIT: usize = 200;

/// Where an uploaded photo is served from. The key is appended to it.
const MEDIA_PATH: &str = "/api/v1/media";

#[derive(Debug, Deserialize)]
pub struct CreateMemory {
    pub lat: f64,
    pub lon: f64,
    pub title: Option<String>,
    pub description: Option<String>,
    /// A third-party media URL. Ignored when `media_key` is set.
    pub media_url: Option<String>,
    /// The key of a photo uploaded to the media endpoint. When it is set the URL is derived
    /// from the key, so a client cannot point a memory at a host it controls.
    pub media_key: Option<String>,
    pub media_type: MediaType,
    pub visibility: Visibility,
    pub unlock_radius_m: f64,
}

#[derive(Debug, Deserialize)]
pub struct UpdateMemory {
    pub title: Option<String>,
    pub description: Option<String>,
    pub visibility: Option<Visibility>,
    pub unlock_radius_m: Option<f64>,
}

#[derive(Debug)]
pub struct Unlocked {
    pub memory: Memory,
    pub distance_m: f64,
}

#[derive(Clone)]
pub struct Memories {
    memories: Arc<dyn MemoryStore>,
    friendships: Arc<dyn FriendshipStore>,
    clock: Arc<dyn Clock>,
}

impl Memories {
    pub fn new(ports: &Ports) -> Self {
        Self {
            memories: ports.memories.clone(),
            friendships: ports.friendships.clone(),
            clock: ports.clock.clone(),
        }
    }

    pub async fn mine(&self, me: Uuid) -> Result<Vec<Memory>> {
        self.memories.owned_by(me).await
    }

    /// Discovery only: callers must not reveal `media_url` from these, that is what `unlock` is for.
    pub async fn nearby(&self, me: Uuid, query: Nearby) -> Result<Vec<Memory>> {
        let area = query.area()?;
        let friends = accepted_friend_ids(self.friendships.as_ref(), me).await?;
        self.memories
            .nearby(me, &friends, &area, NEARBY_LIMIT)
            .await
    }

    pub async fn create(&self, me: Uuid, input: CreateMemory) -> Result<Memory> {
        // An uploaded photo wins over a client-supplied URL: the key is the source of truth
        // and the URL is derived from it.
        let (media_url, media_key) = match input.media_key {
            Some(key) => {
                let key = text::media_key(&key)?;
                (format!("{MEDIA_PATH}/{key}"), Some(key))
            }
            None => (
                text::media_url(input.media_url.as_deref().unwrap_or_default())?,
                None,
            ),
        };
        let memory = NewMemory {
            user_id: me,
            location: Coordinates::in_tunisia(input.lat, input.lon)?,
            unlock_radius: UnlockRadius::new(input.unlock_radius_m)?,
            title: text::title(input.title.as_deref())?,
            description: text::description(input.description.as_deref())?,
            media_url,
            media_key,
            media_type: input.media_type,
            visibility: input.visibility,
        };
        self.memories.insert(memory).await
    }

    pub async fn get(&self, me: Uuid, id: Uuid) -> Result<Memory> {
        let memory = self.find(id).await?;
        self.ensure_visible(me, &memory).await?;
        Ok(memory)
    }

    /// The memory a photo belongs to, when the caller may see it. The photo itself is only
    /// handed out with the key, which is an unguessable UUID.
    pub async fn media_for(&self, me: Uuid, media_key: &str) -> Result<Memory> {
        let key = text::media_key(media_key)?;
        let memory = self
            .memories
            .by_media_key(&key)
            .await?
            .ok_or(AppError::NotFound(Missing::Memory))?;
        self.ensure_visible(me, &memory).await?;
        Ok(memory)
    }

    pub async fn update(&self, me: Uuid, id: Uuid, input: UpdateMemory) -> Result<Memory> {
        let mut memory = self.find(id).await?;
        if memory.user_id != me {
            return Err(AppError::Forbidden);
        }
        let changes = MemoryChanges {
            title: text::title(input.title.as_deref())?,
            description: text::description(input.description.as_deref())?,
            visibility: input.visibility,
            unlock_radius: input.unlock_radius_m.map(UnlockRadius::new).transpose()?,
        };
        memory.apply(changes, self.clock.now());
        self.memories.update(&memory).await?;
        Ok(memory)
    }

    pub async fn delete(&self, me: Uuid, id: Uuid) -> Result<()> {
        if self.memories.delete(id, me).await? {
            Ok(())
        } else {
            Err(AppError::NotFound(Missing::Memory))
        }
    }

    /// The only way to get a memory's media other than owning it.
    pub async fn unlock(&self, me: Uuid, id: Uuid, at: Position) -> Result<Unlocked> {
        let position = Coordinates::in_tunisia(at.lat, at.lon)?;
        let memory = self.find(id).await?;
        self.ensure_visible(me, &memory).await?;
        match memory.unlock_from(position) {
            Ok(distance_m) => Ok(Unlocked { memory, distance_m }),
            Err(too_far) => Err(AppError::TooFar {
                distance_m: too_far.distance_m,
                unlock_radius_m: memory.unlock_radius_m,
            }),
        }
    }

    async fn find(&self, id: Uuid) -> Result<Memory> {
        self.memories
            .get(id)
            .await?
            .ok_or(AppError::NotFound(Missing::Memory))
    }

    async fn ensure_visible(&self, me: Uuid, memory: &Memory) -> Result<()> {
        let friends = memory.needs_friendship_check(me)
            && friendship::are_friends(&self.friendships.between(me, memory.user_id).await?);
        if memory.visible_to(me, friends) {
            Ok(())
        } else {
            Err(AppError::Forbidden)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing::Fakes;

    fn pin(visibility: Visibility) -> CreateMemory {
        CreateMemory {
            lat: 36.8,
            lon: 10.18,
            title: Some("Pinned".into()),
            description: None,
            media_url: Some("https://example.com/media.jpg".into()),
            media_key: None,
            media_type: MediaType::Image,
            visibility,
            unlock_radius_m: 200.0,
        }
    }

    fn at(lat: f64, lon: f64) -> Position {
        Position { lat, lon }
    }

    #[tokio::test]
    async fn create_validates_coordinates_and_radius() {
        let fakes = Fakes::new();
        let memories = Memories::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let paris = CreateMemory {
            lat: 48.8566,
            lon: 2.3522,
            ..pin(Visibility::Public)
        };
        assert_eq!(
            memories.create(me, paris).await.unwrap_err().code(),
            "invalid_coordinates"
        );
        let huge = CreateMemory {
            unlock_radius_m: -5.0,
            ..pin(Visibility::Public)
        };
        assert_eq!(
            memories.create(me, huge).await.unwrap_err().code(),
            "invalid_radius"
        );
        let created = memories.create(me, pin(Visibility::Public)).await.unwrap();
        assert_eq!(memories.mine(me).await.unwrap(), vec![created]);
    }

    #[tokio::test]
    async fn a_memory_without_a_media_url_is_refused() {
        let fakes = Fakes::new();
        let memories = Memories::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let no_media = CreateMemory {
            media_url: None,
            ..pin(Visibility::Public)
        };
        assert_eq!(
            memories.create(me, no_media).await.unwrap_err().code(),
            "invalid_media_url"
        );
    }

    #[tokio::test]
    async fn an_uploaded_photo_wins_over_a_client_supplied_url() {
        let fakes = Fakes::new();
        let memories = Memories::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let upload = CreateMemory {
            media_url: Some("https://evil.example/tracker.gif".into()),
            media_key: Some("abc-123.jpg".into()),
            ..pin(Visibility::Public)
        };
        let created = memories.create(me, upload).await.unwrap();
        assert_eq!(created.media_key.as_deref(), Some("abc-123.jpg"));
        assert_eq!(created.media_url, "/api/v1/media/abc-123.jpg");
    }

    #[tokio::test]
    async fn unlock_needs_the_position_inside_the_radius() {
        let fakes = Fakes::new();
        let memories = Memories::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let memory = memories.create(me, pin(Visibility::Public)).await.unwrap();

        match memories.unlock(me, memory.id, at(36.81, 10.18)).await {
            Err(AppError::TooFar {
                distance_m,
                unlock_radius_m,
            }) => {
                assert!(distance_m > 1000.0);
                assert_eq!(unlock_radius_m, 200.0);
            }
            other => panic!("expected TooFar, got {other:?}"),
        }
        let unlocked = memories
            .unlock(me, memory.id, at(36.8, 10.18))
            .await
            .unwrap();
        assert!(unlocked.distance_m < 1.0);
        let err = memories
            .unlock(me, Uuid::new_v4(), at(36.8, 10.18))
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::NotFound(Missing::Memory)));
    }

    #[tokio::test]
    async fn friends_only_memories_need_an_accepted_friendship() {
        let fakes = Fakes::new();
        let memories = Memories::new(&fakes.ports());
        let owner = fakes.user("owner@example.com").await;
        let friend = fakes.user("friend@example.com").await;
        let memory = memories
            .create(owner, pin(Visibility::Friends))
            .await
            .unwrap();

        let denied = memories.get(friend, memory.id).await.unwrap_err();
        assert!(matches!(denied, AppError::Forbidden));
        let near = Nearby {
            lat: 36.8,
            lon: 10.18,
            radius_m: Some(1000.0),
        };
        assert!(memories.nearby(friend, near).await.unwrap().is_empty());

        fakes.befriend(owner, friend).await;
        assert!(memories.get(friend, memory.id).await.is_ok());
        assert_eq!(memories.nearby(friend, near).await.unwrap().len(), 1);
    }

    #[tokio::test]
    async fn nearby_rejects_a_radius_above_the_cap() {
        let fakes = Fakes::new();
        let memories = Memories::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let wide = Nearby {
            lat: 36.8,
            lon: 10.2,
            radius_m: Some(999_999.0),
        };
        assert_eq!(
            memories.nearby(me, wide).await.unwrap_err().code(),
            "invalid_radius"
        );
    }

    #[tokio::test]
    async fn only_the_owner_updates_or_deletes() {
        let fakes = Fakes::new();
        let memories = Memories::new(&fakes.ports());
        let owner = fakes.user("owner@example.com").await;
        let other = fakes.user("other@example.com").await;
        let memory = memories
            .create(owner, pin(Visibility::Public))
            .await
            .unwrap();
        let change = || UpdateMemory {
            title: None,
            description: Some("new".into()),
            visibility: None,
            unlock_radius_m: Some(500.0),
        };

        let err = memories
            .update(other, memory.id, change())
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::Forbidden));
        let updated = memories.update(owner, memory.id, change()).await.unwrap();
        assert_eq!(updated.title.as_deref(), Some("Pinned"));
        assert_eq!(updated.description.as_deref(), Some("new"));
        assert_eq!(updated.unlock_radius_m, 500.0);
        assert_eq!(updated.updated_at, fakes.now());
        assert_eq!(memories.get(owner, memory.id).await.unwrap(), updated);

        assert!(memories.delete(other, memory.id).await.is_err());
        memories.delete(owner, memory.id).await.unwrap();
        assert!(memories.mine(owner).await.unwrap().is_empty());
    }
}
