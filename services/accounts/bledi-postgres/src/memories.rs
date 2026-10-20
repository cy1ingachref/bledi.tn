use async_trait::async_trait;
use bledi_application::ports::{MemoryStore, NewMemory, Result};
use bledi_domain::geo::SearchArea;
use bledi_domain::memory::{MediaType, Memory, Visibility};
use chrono::{DateTime, Utc};
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

use crate::{bind_area, distance_m, in_area, internal};

macro_rules! columns {
    () => {
        "id, user_id, lat, lon, title, description, media_url, media_key, media_type::text AS media_type,
         visibility::text AS visibility, unlock_radius_m, created_at, updated_at"
    };
}

#[derive(FromRow)]
struct MemoryRow {
    id: Uuid,
    user_id: Uuid,
    lat: f64,
    lon: f64,
    title: Option<String>,
    description: Option<String>,
    media_url: String,
    media_key: Option<String>,
    #[sqlx(try_from = "String")]
    media_type: MediaType,
    #[sqlx(try_from = "String")]
    visibility: Visibility,
    unlock_radius_m: f64,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl From<MemoryRow> for Memory {
    fn from(row: MemoryRow) -> Self {
        Memory {
            id: row.id,
            user_id: row.user_id,
            lat: row.lat,
            lon: row.lon,
            title: row.title,
            description: row.description,
            media_url: row.media_url,
            media_key: row.media_key,
            media_type: row.media_type,
            visibility: row.visibility,
            unlock_radius_m: row.unlock_radius_m,
            created_at: row.created_at,
            updated_at: row.updated_at,
        }
    }
}

#[derive(Clone)]
pub struct PostgresMemoryStore {
    pool: PgPool,
}

impl PostgresMemoryStore {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl MemoryStore for PostgresMemoryStore {
    async fn insert(&self, new: NewMemory) -> Result<Memory> {
        sqlx::query_as::<_, MemoryRow>(concat!(
            "INSERT INTO memories
                (user_id, lat, lon, title, description, media_url, media_key, media_type, visibility, unlock_radius_m)
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8::media_type, $9::visibility, $10)
             RETURNING ",
            columns!()
        ))
        .bind(new.user_id)
        .bind(new.location.lat())
        .bind(new.location.lon())
        .bind(new.title)
        .bind(new.description)
        .bind(new.media_url)
        .bind(new.media_key)
        .bind(new.media_type.as_str())
        .bind(new.visibility.as_str())
        .bind(new.unlock_radius.metres())
        .fetch_one(&self.pool)
        .await
        .map(Memory::from)
        .map_err(internal)
    }

    async fn get(&self, id: Uuid) -> Result<Option<Memory>> {
        sqlx::query_as::<_, MemoryRow>(concat!(
            "SELECT ",
            columns!(),
            " FROM memories WHERE id = $1"
        ))
        .bind(id)
        .fetch_optional(&self.pool)
        .await
        .map(|row| row.map(Memory::from))
        .map_err(internal)
    }

    async fn by_media_key(&self, media_key: &str) -> Result<Option<Memory>> {
        sqlx::query_as::<_, MemoryRow>(concat!(
            "SELECT ",
            columns!(),
            " FROM memories WHERE media_key = $1"
        ))
        .bind(media_key)
        .fetch_optional(&self.pool)
        .await
        .map(|row| row.map(Memory::from))
        .map_err(internal)
    }

    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<Memory>> {
        sqlx::query_as::<_, MemoryRow>(concat!(
            "SELECT ",
            columns!(),
            " FROM memories WHERE user_id = $1 ORDER BY created_at DESC"
        ))
        .bind(user_id)
        .fetch_all(&self.pool)
        .await
        .map(|rows| rows.into_iter().map(Memory::from).collect())
        .map_err(internal)
    }

    async fn nearby(
        &self,
        viewer: Uuid,
        friends: &[Uuid],
        area: &SearchArea,
        limit: usize,
    ) -> Result<Vec<Memory>> {
        let query = sqlx::query_as::<_, MemoryRow>(concat!(
            "SELECT ",
            columns!(),
            " FROM (SELECT *, ",
            distance_m!(),
            " AS distance_m FROM memories WHERE ",
            in_area!(),
            " AND (user_id = $10 OR visibility = 'public'
                   OR (visibility = 'friends' AND user_id = ANY($11)))
             ) AS candidates
             WHERE distance_m <= $7
             ORDER BY distance_m
             LIMIT $9"
        ));
        bind_area(query, area, limit)
            .bind(viewer)
            .bind(friends)
            .fetch_all(&self.pool)
            .await
            .map(|rows| rows.into_iter().map(Memory::from).collect())
            .map_err(internal)
    }

    async fn update(&self, memory: &Memory) -> Result<()> {
        sqlx::query(
            "UPDATE memories
             SET title = $1, description = $2, visibility = $3::visibility,
                 unlock_radius_m = $4, updated_at = $5
             WHERE id = $6",
        )
        .bind(&memory.title)
        .bind(&memory.description)
        .bind(memory.visibility.as_str())
        .bind(memory.unlock_radius_m)
        .bind(memory.updated_at)
        .bind(memory.id)
        .execute(&self.pool)
        .await
        .map_err(internal)?;
        Ok(())
    }

    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool> {
        let result = sqlx::query("DELETE FROM memories WHERE id = $1 AND user_id = $2")
            .bind(id)
            .bind(user_id)
            .execute(&self.pool)
            .await
            .map_err(internal)?;
        Ok(result.rows_affected() > 0)
    }
}
