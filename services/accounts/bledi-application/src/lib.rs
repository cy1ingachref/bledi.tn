pub mod accounts;
mod error;
pub mod favorites;
pub mod friendships;
pub mod memories;
pub mod ports;
#[cfg(any(test, feature = "testing"))]
pub mod testing;

use std::sync::Arc;

use bledi_domain::geo::{Coordinates, SearchArea};
use serde::Deserialize;

pub use error::{AppError, Missing};

use ports::{
    Clock, FavoriteStore, FriendshipStore, LocationShareStore, MemoryStore, PasswordHasher,
    TokenIssuer, UserStore,
};

#[derive(Debug, Clone, Copy, Deserialize)]
pub struct Nearby {
    pub lat: f64,
    pub lon: f64,
    pub radius_m: Option<f64>,
}

impl Nearby {
    fn area(self) -> Result<SearchArea, AppError> {
        Ok(SearchArea::new(
            Coordinates::in_tunisia(self.lat, self.lon)?,
            self.radius_m,
        )?)
    }
}

#[derive(Debug, Clone, Copy, Deserialize)]
pub struct Position {
    pub lat: f64,
    pub lon: f64,
}

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
