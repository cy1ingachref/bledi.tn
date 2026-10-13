use chrono::{DateTime, Utc};
use serde::Serialize;
use uuid::Uuid;

use crate::string_enum;

string_enum!(FavoriteKind {
    Station => "station",
    Line => "line",
    Place => "place",
});

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Favorite {
    pub id: Uuid,
    pub user_id: Uuid,
    pub kind: FavoriteKind,
    pub ref_id: String,
    pub label: Option<String>,
    pub created_at: DateTime<Utc>,
}
