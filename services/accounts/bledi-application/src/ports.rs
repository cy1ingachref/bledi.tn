use async_trait::async_trait;
use bledi_domain::favorite::{Favorite, FavoriteKind};
use bledi_domain::friendship::Friendship;
use bledi_domain::geo::{Coordinates, SearchArea, UnlockRadius};
use bledi_domain::location_share::LocationShare;
use bledi_domain::memory::{MediaType, Memory, Visibility};
use bledi_domain::user::User;
use chrono::{DateTime, Utc};
use uuid::Uuid;

use crate::AppError;

pub type Result<T> = std::result::Result<T, AppError>;

pub struct NewUser {
    pub email: String,
    pub password_hash: String,
    pub display_name: Option<String>,
}

pub struct StoredUser {
    pub user: User,
    pub password_hash: String,
}

pub struct NewMemory {
    pub user_id: Uuid,
    pub location: Coordinates,
    pub title: Option<String>,
    pub description: Option<String>,
    pub media_url: String,
    pub media_type: MediaType,
    pub visibility: Visibility,
    pub unlock_radius: UnlockRadius,
}

pub struct NewFavorite {
    pub user_id: Uuid,
    pub kind: FavoriteKind,
    pub ref_id: String,
    pub label: Option<String>,
}

pub struct NewLocationShare {
    pub user_id: Uuid,
    pub location: Coordinates,
    pub accuracy_m: Option<f64>,
    pub note: Option<String>,
    pub is_active: bool,
    pub expires_at: DateTime<Utc>,
}

#[async_trait]
pub trait UserStore: Send + Sync {
    /// Fails with `EmailTaken` when the email is already registered.
    async fn insert(&self, user: NewUser) -> Result<User>;
    async fn get(&self, id: Uuid) -> Result<Option<User>>;
    async fn get_many(&self, ids: &[Uuid]) -> Result<Vec<User>>;
    async fn find_by_email(&self, email: &str) -> Result<Option<StoredUser>>;
}

#[async_trait]
pub trait MemoryStore: Send + Sync {
    async fn insert(&self, memory: NewMemory) -> Result<Memory>;
    async fn get(&self, id: Uuid) -> Result<Option<Memory>>;
    /// Newest first.
    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<Memory>>;
    /// Memories `viewer` may see inside `area`, nearest first.
    async fn nearby(
        &self,
        viewer: Uuid,
        friends: &[Uuid],
        area: &SearchArea,
        limit: usize,
    ) -> Result<Vec<Memory>>;
    async fn update(&self, memory: &Memory) -> Result<()>;
    /// False when there is no such memory owned by `user_id`.
    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool>;
}

#[async_trait]
pub trait FriendshipStore: Send + Sync {
    /// The rows linking `a` and `b`, in either direction.
    async fn between(&self, a: Uuid, b: Uuid) -> Result<Vec<Friendship>>;
    /// Every row `user_id` is part of.
    async fn of(&self, user_id: Uuid) -> Result<Vec<Friendship>>;
    /// Fails with `RequestPending` when `from` already asked `to`.
    async fn request(&self, from: Uuid, to: Uuid) -> Result<()>;
    /// False when there is no pending request from `requester` to `recipient`.
    async fn accept(&self, requester: Uuid, recipient: Uuid) -> Result<bool>;
    /// False when `a` and `b` are not linked.
    async fn remove(&self, a: Uuid, b: Uuid) -> Result<bool>;
}

#[async_trait]
pub trait FavoriteStore: Send + Sync {
    /// Newest first.
    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<Favorite>>;
    /// Saving the same kind and ref_id again replaces the label.
    async fn upsert(&self, favorite: NewFavorite) -> Result<Favorite>;
    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool>;
}

#[async_trait]
pub trait LocationShareStore: Send + Sync {
    /// Most recently updated first.
    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<LocationShare>>;
    /// Live shares of `owners` inside `area`, nearest first.
    async fn nearby(
        &self,
        owners: &[Uuid],
        area: &SearchArea,
        now: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<LocationShare>>;
    async fn insert(&self, share: NewLocationShare) -> Result<LocationShare>;
    async fn get(&self, id: Uuid) -> Result<Option<LocationShare>>;
    async fn update(&self, share: &LocationShare) -> Result<()>;
    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool>;
}

#[async_trait]
pub trait PasswordHasher: Send + Sync {
    async fn hash(&self, password: &str) -> Result<String>;
    /// With no hash, still spends the time of a real check and returns false, so an unknown
    /// email cannot be told apart from a wrong password by timing.
    async fn verify(&self, password: &str, hash: Option<&str>) -> Result<bool>;
}

pub trait TokenIssuer: Send + Sync {
    fn issue(&self, user: &User) -> Result<String>;
    /// The user id the token was issued to. Fails with `Unauthorized`.
    fn verify(&self, token: &str) -> Result<Uuid>;
}

pub trait Clock: Send + Sync {
    fn now(&self) -> DateTime<Utc>;
}
