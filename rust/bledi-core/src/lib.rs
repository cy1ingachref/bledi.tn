//! bledi-core: shared types and data models for the bledi.tn transit app.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ── Transport modes ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, sqlx::Type)]
#[serde(rename_all = "lowercase")]
#[sqlx(type_name = "transport_mode", rename_all = "lowercase")]
pub enum TransportMode {
    Bus,
    Metro,
    Tram,
    Train,
    Rfr,
    Taxi,
    Louaj,
    Walk,
}

impl TransportMode {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Bus => "bus",
            Self::Metro => "metro",
            Self::Tram => "tram",
            Self::Train => "train",
            Self::Rfr => "rfr",
            Self::Taxi => "taxi",
            Self::Louaj => "louaj",
            Self::Walk => "walk",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "bus" => Some(Self::Bus),
            "metro" => Some(Self::Metro),
            "tram" => Some(Self::Tram),
            "train" => Some(Self::Train),
            "rfr" => Some(Self::Rfr),
            "taxi" => Some(Self::Taxi),
            "louaj" => Some(Self::Louaj),
            "walk" => Some(Self::Walk),
            _ => None,
        }
    }
}

// ── Station ─────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Station {
    pub id: String,
    pub name: String,
    pub lat: f64,
    pub lon: f64,
    pub modes: Vec<TransportMode>,
    pub city: Option<String>,
}

// ── Line ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Line {
    pub id: String,
    pub number: String,
    pub name: String,
    pub mode: TransportMode,
    pub operator: Option<String>,
    pub color: Option<String>,
    pub station_ids: Vec<String>,
}

// ── User ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct User {
    pub id: Uuid,
    pub email: String,
    #[serde(skip_serializing)]
    pub password_hash: String,
    pub display_name: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PublicUser {
    pub id: Uuid,
    pub email: String,
    pub display_name: Option<String>,
    pub created_at: DateTime<Utc>,
}

impl From<User> for PublicUser {
    fn from(u: User) -> Self {
        Self {
            id: u.id,
            email: u.email,
            display_name: u.display_name,
            created_at: u.created_at,
        }
    }
}

// ── Memory (geo-pinned) ─────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, sqlx::Type)]
#[serde(rename_all = "lowercase")]
#[sqlx(type_name = "visibility", rename_all = "lowercase")]
pub enum Visibility {
    Public,
    Friends,
    Private,
}

impl Visibility {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Public => "public",
            Self::Friends => "friends",
            Self::Private => "private",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, sqlx::Type)]
#[serde(rename_all = "lowercase")]
#[sqlx(type_name = "media_type", rename_all = "lowercase")]
pub enum MediaType {
    Image,
    Video,
}

impl MediaType {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Image => "image",
            Self::Video => "video",
        }
    }
}

// ── Favorite ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Favorite {
    pub id: Uuid,
    pub user_id: Uuid,
    pub kind: FavoriteKind,
    pub ref_id: String,
    pub label: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, sqlx::Type)]
#[serde(rename_all = "lowercase")]
#[sqlx(type_name = "favorite_kind", rename_all = "lowercase")]
pub enum FavoriteKind {
    Station,
    Line,
    Place,
}

impl FavoriteKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Station => "station",
            Self::Line => "line",
            Self::Place => "place",
        }
    }
}

// ── Location sharing ────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
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

// ── API request/response types ──────────────────────────────────────────────

#[derive(Debug, Deserialize)]
pub struct RegisterRequest {
    pub email: String,
    pub password: String,
    pub display_name: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub email: String,
    pub password: String,
}

#[derive(Debug, Serialize)]
pub struct AuthResponse {
    pub token: String,
    pub user: PublicUser,
}

#[derive(Debug, Deserialize)]
pub struct CreateMemoryRequest {
    pub lat: f64,
    pub lon: f64,
    pub title: Option<String>,
    pub description: Option<String>,
    pub media_url: String,
    pub media_type: MediaType,
    pub visibility: Visibility,
    pub unlock_radius_m: f64,
}

#[derive(Debug, Deserialize)]
pub struct UpdateMemoryRequest {
    pub title: Option<String>,
    pub description: Option<String>,
    pub visibility: Option<Visibility>,
    pub unlock_radius_m: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub struct CreateFavoriteRequest {
    pub kind: FavoriteKind,
    pub ref_id: String,
    pub label: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UpdateLocationShareRequest {
    pub lat: f64,
    pub lon: f64,
    pub accuracy_m: Option<f64>,
    pub note: Option<String>,
    pub is_active: bool,
    pub expires_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Deserialize)]
pub struct NearbyMemoriesQuery {
    pub lat: f64,
    pub lon: f64,
    pub radius_m: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub struct NearbySharesQuery {
    pub lat: f64,
    pub lon: f64,
    pub radius_m: Option<f64>,
}

// ── Geo helpers ─────────────────────────────────────────────────────────────

/// Haversine distance in meters.
pub fn haversine_m(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    const EARTH_R_M: f64 = 6_371_000.0;
    let d_lat = (lat2 - lat1).to_radians();
    let d_lon = (lon2 - lon1).to_radians();
    let a = (d_lat / 2.0).sin().powi(2)
        + lat1.to_radians().cos() * lat2.to_radians().cos() * (d_lon / 2.0).sin().powi(2);
    2.0 * EARTH_R_M * a.sqrt().atan2((1.0 - a).sqrt())
}
