//! In-memory fakes of every port, for use case and HTTP tests.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use bledi_domain::favorite::Favorite;
use bledi_domain::friendship::{Friendship, FriendshipStatus};
use bledi_domain::geo::SearchArea;
use bledi_domain::location_share::LocationShare;
use bledi_domain::memory::Memory;
use bledi_domain::user::User;
use chrono::{DateTime, Utc};
use uuid::Uuid;

use crate::ports::*;
use crate::{AppError, Ports};

fn nearest<T>(
    rows: Vec<T>,
    area: &SearchArea,
    at: impl Fn(&T) -> (f64, f64),
    limit: usize,
) -> Vec<T> {
    let mut found: Vec<(f64, T)> = rows
        .into_iter()
        .filter_map(|row| {
            let (lat, lon) = at(&row);
            area.distance_to(lat, lon).map(|d| (d, row))
        })
        .collect();
    found.sort_by(|a, b| a.0.total_cmp(&b.0));
    found.into_iter().take(limit).map(|(_, row)| row).collect()
}

pub struct FixedClock(pub DateTime<Utc>);

impl Clock for FixedClock {
    fn now(&self) -> DateTime<Utc> {
        self.0
    }
}

#[derive(Default)]
pub struct FakePasswordHasher {
    unmatched: AtomicUsize,
}

impl FakePasswordHasher {
    /// How many checks ran without a stored hash.
    pub fn unmatched_checks(&self) -> usize {
        self.unmatched.load(Ordering::Relaxed)
    }
}

#[async_trait]
impl PasswordHasher for FakePasswordHasher {
    async fn hash(&self, password: &str) -> Result<String> {
        Ok(format!("fake-hash:{password}"))
    }

    async fn verify(&self, password: &str, hash: Option<&str>) -> Result<bool> {
        match hash {
            Some(hash) => Ok(hash == format!("fake-hash:{password}")),
            None => {
                self.unmatched.fetch_add(1, Ordering::Relaxed);
                Ok(false)
            }
        }
    }
}

pub struct FakeTokenIssuer;

impl TokenIssuer for FakeTokenIssuer {
    fn issue(&self, user: &User) -> Result<String> {
        Ok(format!("fake-token:{}", user.id))
    }

    fn verify(&self, token: &str) -> Result<Uuid> {
        token
            .strip_prefix("fake-token:")
            .and_then(|id| Uuid::parse_str(id).ok())
            .ok_or(AppError::Unauthorized("Invalid or expired token"))
    }
}

#[derive(Default)]
pub struct InMemoryUserStore(Mutex<Vec<(User, String)>>);

#[async_trait]
impl UserStore for InMemoryUserStore {
    async fn insert(&self, new: NewUser) -> Result<User> {
        let mut users = self.0.lock().unwrap();
        if users.iter().any(|(u, _)| u.email == new.email) {
            return Err(AppError::EmailTaken);
        }
        let user = User {
            id: Uuid::new_v4(),
            email: new.email,
            display_name: new.display_name,
            created_at: Utc::now(),
        };
        users.push((user.clone(), new.password_hash));
        Ok(user)
    }

    async fn get(&self, id: Uuid) -> Result<Option<User>> {
        let users = self.0.lock().unwrap();
        Ok(users
            .iter()
            .find(|(u, _)| u.id == id)
            .map(|(u, _)| u.clone()))
    }

    async fn get_many(&self, ids: &[Uuid]) -> Result<Vec<User>> {
        let users = self.0.lock().unwrap();
        Ok(users
            .iter()
            .filter(|(u, _)| ids.contains(&u.id))
            .map(|(u, _)| u.clone())
            .collect())
    }

    async fn find_by_email(&self, email: &str) -> Result<Option<StoredUser>> {
        let users = self.0.lock().unwrap();
        Ok(users
            .iter()
            .find(|(u, _)| u.email == email)
            .map(|(user, hash)| StoredUser {
                user: user.clone(),
                password_hash: hash.clone(),
            }))
    }
}

#[derive(Default)]
pub struct InMemoryMemoryStore(Mutex<Vec<Memory>>);

#[async_trait]
impl MemoryStore for InMemoryMemoryStore {
    async fn insert(&self, new: NewMemory) -> Result<Memory> {
        let now = Utc::now();
        let memory = Memory {
            id: Uuid::new_v4(),
            user_id: new.user_id,
            lat: new.location.lat(),
            lon: new.location.lon(),
            title: new.title,
            description: new.description,
            media_url: new.media_url,
            media_key: new.media_key,
            media_type: new.media_type,
            visibility: new.visibility,
            unlock_radius_m: new.unlock_radius.metres(),
            created_at: now,
            updated_at: now,
        };
        self.0.lock().unwrap().push(memory.clone());
        Ok(memory)
    }

    async fn get(&self, id: Uuid) -> Result<Option<Memory>> {
        Ok(self.0.lock().unwrap().iter().find(|m| m.id == id).cloned())
    }

    async fn by_media_key(&self, media_key: &str) -> Result<Option<Memory>> {
        Ok(self
            .0
            .lock()
            .unwrap()
            .iter()
            .find(|m| m.media_key.as_deref() == Some(media_key))
            .cloned())
    }

    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<Memory>> {
        let memories = self.0.lock().unwrap();
        Ok(memories
            .iter()
            .rev()
            .filter(|m| m.user_id == user_id)
            .cloned()
            .collect())
    }

    async fn nearby(
        &self,
        viewer: Uuid,
        friends: &[Uuid],
        area: &SearchArea,
        limit: usize,
    ) -> Result<Vec<Memory>> {
        let visible = self
            .0
            .lock()
            .unwrap()
            .iter()
            .filter(|m| m.visible_to(viewer, friends.contains(&m.user_id)))
            .cloned()
            .collect();
        Ok(nearest(visible, area, |m| (m.lat, m.lon), limit))
    }

    async fn update(&self, memory: &Memory) -> Result<()> {
        let mut memories = self.0.lock().unwrap();
        if let Some(stored) = memories.iter_mut().find(|m| m.id == memory.id) {
            *stored = memory.clone();
        }
        Ok(())
    }

    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool> {
        let mut memories = self.0.lock().unwrap();
        let before = memories.len();
        memories.retain(|m| !(m.id == id && m.user_id == user_id));
        Ok(memories.len() < before)
    }
}

#[derive(Default)]
pub struct InMemoryFriendshipStore(Mutex<Vec<Friendship>>);

fn links(f: &Friendship, a: Uuid, b: Uuid) -> bool {
    (f.user_id == a && f.friend_id == b) || (f.user_id == b && f.friend_id == a)
}

#[async_trait]
impl FriendshipStore for InMemoryFriendshipStore {
    async fn between(&self, a: Uuid, b: Uuid) -> Result<Vec<Friendship>> {
        let rows = self.0.lock().unwrap();
        Ok(rows.iter().filter(|f| links(f, a, b)).cloned().collect())
    }

    async fn of(&self, user_id: Uuid) -> Result<Vec<Friendship>> {
        let rows = self.0.lock().unwrap();
        Ok(rows
            .iter()
            .filter(|f| f.user_id == user_id || f.friend_id == user_id)
            .cloned()
            .collect())
    }

    async fn request(&self, from: Uuid, to: Uuid) -> Result<()> {
        let mut rows = self.0.lock().unwrap();
        if rows.iter().any(|f| f.user_id == from && f.friend_id == to) {
            return Err(AppError::RequestPending);
        }
        rows.push(Friendship {
            user_id: from,
            friend_id: to,
            status: FriendshipStatus::Pending,
            created_at: Utc::now(),
        });
        Ok(())
    }

    async fn accept(&self, requester: Uuid, recipient: Uuid) -> Result<bool> {
        let mut rows = self.0.lock().unwrap();
        let pending = rows.iter_mut().find(|f| {
            f.user_id == requester
                && f.friend_id == recipient
                && f.status == FriendshipStatus::Pending
        });
        Ok(pending
            .map(|f| f.status = FriendshipStatus::Accepted)
            .is_some())
    }

    async fn remove(&self, a: Uuid, b: Uuid) -> Result<bool> {
        let mut rows = self.0.lock().unwrap();
        let before = rows.len();
        rows.retain(|f| !links(f, a, b));
        Ok(rows.len() < before)
    }
}

#[derive(Default)]
pub struct InMemoryFavoriteStore(Mutex<Vec<Favorite>>);

#[async_trait]
impl FavoriteStore for InMemoryFavoriteStore {
    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<Favorite>> {
        let favorites = self.0.lock().unwrap();
        Ok(favorites
            .iter()
            .rev()
            .filter(|f| f.user_id == user_id)
            .cloned()
            .collect())
    }

    async fn upsert(&self, new: NewFavorite) -> Result<Favorite> {
        let mut favorites = self.0.lock().unwrap();
        let same = |f: &&mut Favorite| {
            f.user_id == new.user_id && f.kind == new.kind && f.ref_id == new.ref_id
        };
        if let Some(existing) = favorites.iter_mut().find(same) {
            existing.label = new.label;
            return Ok(existing.clone());
        }
        let favorite = Favorite {
            id: Uuid::new_v4(),
            user_id: new.user_id,
            kind: new.kind,
            ref_id: new.ref_id,
            label: new.label,
            created_at: Utc::now(),
        };
        favorites.push(favorite.clone());
        Ok(favorite)
    }

    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool> {
        let mut favorites = self.0.lock().unwrap();
        let before = favorites.len();
        favorites.retain(|f| !(f.id == id && f.user_id == user_id));
        Ok(favorites.len() < before)
    }
}

#[derive(Default)]
pub struct InMemoryLocationShareStore(Mutex<Vec<LocationShare>>);

#[async_trait]
impl LocationShareStore for InMemoryLocationShareStore {
    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<LocationShare>> {
        let shares = self.0.lock().unwrap();
        let mut mine: Vec<_> = shares
            .iter()
            .rev()
            .filter(|s| s.user_id == user_id)
            .cloned()
            .collect();
        mine.sort_by_key(|s| std::cmp::Reverse(s.updated_at));
        Ok(mine)
    }

    async fn nearby(
        &self,
        owners: &[Uuid],
        area: &SearchArea,
        now: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<LocationShare>> {
        let live = self
            .0
            .lock()
            .unwrap()
            .iter()
            .filter(|s| owners.contains(&s.user_id) && s.is_live(now))
            .cloned()
            .collect();
        Ok(nearest(live, area, |s| (s.lat, s.lon), limit))
    }

    async fn insert(&self, new: NewLocationShare) -> Result<LocationShare> {
        let now = Utc::now();
        let share = LocationShare {
            id: Uuid::new_v4(),
            user_id: new.user_id,
            lat: new.location.lat(),
            lon: new.location.lon(),
            accuracy_m: new.accuracy_m,
            note: new.note,
            is_active: new.is_active,
            expires_at: Some(new.expires_at),
            created_at: now,
            updated_at: now,
        };
        self.0.lock().unwrap().push(share.clone());
        Ok(share)
    }

    async fn get(&self, id: Uuid) -> Result<Option<LocationShare>> {
        Ok(self.0.lock().unwrap().iter().find(|s| s.id == id).cloned())
    }

    async fn update(&self, share: &LocationShare) -> Result<()> {
        let mut shares = self.0.lock().unwrap();
        if let Some(stored) = shares.iter_mut().find(|s| s.id == share.id) {
            *stored = share.clone();
        }
        Ok(())
    }

    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool> {
        let mut shares = self.0.lock().unwrap();
        let before = shares.len();
        shares.retain(|s| !(s.id == id && s.user_id == user_id));
        Ok(shares.len() < before)
    }
}

/// One fake per port, shared by everything built from `ports()` so a test can seed and inspect state.
pub struct Fakes {
    pub users: Arc<InMemoryUserStore>,
    pub memories: Arc<InMemoryMemoryStore>,
    pub friendships: Arc<InMemoryFriendshipStore>,
    pub favorites: Arc<InMemoryFavoriteStore>,
    pub location_shares: Arc<InMemoryLocationShareStore>,
    pub hasher: Arc<FakePasswordHasher>,
    pub clock: Arc<FixedClock>,
}

impl Default for Fakes {
    fn default() -> Self {
        Self::new()
    }
}

impl Fakes {
    pub fn new() -> Self {
        Self {
            users: Arc::default(),
            memories: Arc::default(),
            friendships: Arc::default(),
            favorites: Arc::default(),
            location_shares: Arc::default(),
            hasher: Arc::default(),
            clock: Arc::new(FixedClock(Utc::now())),
        }
    }

    pub fn ports(&self) -> Ports {
        Ports {
            users: self.users.clone(),
            memories: self.memories.clone(),
            friendships: self.friendships.clone(),
            favorites: self.favorites.clone(),
            location_shares: self.location_shares.clone(),
            hasher: self.hasher.clone(),
            tokens: Arc::new(FakeTokenIssuer),
            clock: self.clock.clone(),
        }
    }

    pub fn now(&self) -> DateTime<Utc> {
        self.clock.0
    }

    /// Registers a user whose password is `test123456`.
    pub async fn user(&self, email: &str) -> Uuid {
        let new = NewUser {
            email: email.into(),
            password_hash: self.hasher.hash("test123456").await.unwrap(),
            display_name: None,
        };
        self.users.insert(new).await.unwrap().id
    }

    pub async fn befriend(&self, a: Uuid, b: Uuid) {
        self.friendships.request(a, b).await.unwrap();
        self.friendships.accept(a, b).await.unwrap();
    }
}
