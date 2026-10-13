mod error;
pub mod ports;

use std::sync::Arc;

pub use error::{AppError, Missing};

use ports::{
    Clock, FavoriteStore, FriendshipStore, LocationShareStore, MemoryStore, PasswordHasher,
    TokenIssuer, UserStore,
};

pub struct Ports {
    pub users: Arc<dyn UserStore>,
    pub memories: Arc<dyn MemoryStore>,
    pub friendships: Arc<dyn FriendshipStore>,
    pub favorites: Arc<dyn FavoriteStore>,
    pub location_shares: Arc<dyn LocationShareStore>,
    pub hasher: Arc<dyn PasswordHasher>,
    pub tokens: Arc<dyn TokenIssuer>,
    pub clock: Arc<dyn Clock>,
}
