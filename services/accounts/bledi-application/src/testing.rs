//! In-memory fakes of every port, for use case and HTTP tests.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use async_trait::async_trait;
use bledi_domain::friendship::{Friendship, FriendshipStatus};
use bledi_domain::geo::SearchArea;
use bledi_domain::memory::Memory;
use bledi_domain::user::User;
use chrono::{DateTime, Utc};
use uuid::Uuid;

use crate::ports::*;
use crate::AppError;

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
