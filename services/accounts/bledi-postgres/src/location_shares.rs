use async_trait::async_trait;
use bledi_application::ports::{LocationShareStore, NewLocationShare, Result};
use bledi_domain::geo::SearchArea;
use bledi_domain::location_share::LocationShare;
use chrono::{DateTime, Utc};
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

use crate::{bind_area, distance_m, in_area, internal};

macro_rules! columns {
    () => {
        "id, user_id, lat, lon, accuracy_m, note, is_active, expires_at, created_at, updated_at"
    };
}

#[derive(FromRow)]
struct LocationShareRow {
    id: Uuid,
    user_id: Uuid,
    lat: f64,
    lon: f64,
    accuracy_m: Option<f64>,
    note: Option<String>,
    is_active: bool,
    expires_at: Option<DateTime<Utc>>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl From<LocationShareRow> for LocationShare {
    fn from(row: LocationShareRow) -> Self {
        LocationShare {
            id: row.id,
            user_id: row.user_id,
            lat: row.lat,
            lon: row.lon,
            accuracy_m: row.accuracy_m,
            note: row.note,
            is_active: row.is_active,
            expires_at: row.expires_at,
            created_at: row.created_at,
            updated_at: row.updated_at,
        }
    }
}

fn shares(rows: Vec<LocationShareRow>) -> Vec<LocationShare> {
    rows.into_iter().map(LocationShare::from).collect()
}

#[derive(Clone)]
pub struct PostgresLocationShareStore {
    pool: PgPool,
}

impl PostgresLocationShareStore {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl LocationShareStore for PostgresLocationShareStore {
    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<LocationShare>> {
        sqlx::query_as::<_, LocationShareRow>(concat!(
            "SELECT ",
            columns!(),
            " FROM location_shares WHERE user_id = $1 ORDER BY updated_at DESC"
        ))
        .bind(user_id)
        .fetch_all(&self.pool)
        .await
        .map(shares)
        .map_err(internal)
    }

    async fn nearby(
        &self,
        owners: &[Uuid],
        area: &SearchArea,
        now: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<LocationShare>> {
        let query = sqlx::query_as::<_, LocationShareRow>(concat!(
            "SELECT ",
            columns!(),
            " FROM (SELECT *, ",
            distance_m!(),
            " AS distance_m FROM location_shares WHERE ",
            in_area!(),
            " AND is_active AND (expires_at IS NULL OR expires_at > $10) AND user_id = ANY($11)
             ) AS candidates
             WHERE distance_m <= $7
             ORDER BY distance_m
             LIMIT $9"
        ));
        bind_area(query, area, limit)
            .bind(now)
            .bind(owners)
            .fetch_all(&self.pool)
            .await
            .map(shares)
            .map_err(internal)
    }

    async fn insert(&self, new: NewLocationShare) -> Result<LocationShare> {
        sqlx::query_as::<_, LocationShareRow>(concat!(
            "INSERT INTO location_shares (user_id, lat, lon, accuracy_m, note, is_active, expires_at)
             VALUES ($1, $2, $3, $4, $5, $6, $7)
             RETURNING ",
            columns!()
        ))
        .bind(new.user_id)
        .bind(new.location.lat())
        .bind(new.location.lon())
        .bind(new.accuracy_m)
        .bind(new.note)
        .bind(new.is_active)
        .bind(new.expires_at)
        .fetch_one(&self.pool)
        .await
        .map(LocationShare::from)
        .map_err(internal)
    }

    async fn get(&self, id: Uuid) -> Result<Option<LocationShare>> {
        sqlx::query_as::<_, LocationShareRow>(concat!(
            "SELECT ",
            columns!(),
            " FROM location_shares WHERE id = $1"
        ))
        .bind(id)
        .fetch_optional(&self.pool)
        .await
        .map(|row| row.map(LocationShare::from))
        .map_err(internal)
    }

    async fn update(&self, share: &LocationShare) -> Result<()> {
        sqlx::query(
            "UPDATE location_shares
             SET lat = $1, lon = $2, accuracy_m = $3, note = $4, is_active = $5,
                 expires_at = $6, updated_at = $7
             WHERE id = $8",
        )
        .bind(share.lat)
        .bind(share.lon)
        .bind(share.accuracy_m)
        .bind(&share.note)
        .bind(share.is_active)
        .bind(share.expires_at)
        .bind(share.updated_at)
        .bind(share.id)
        .execute(&self.pool)
        .await
        .map_err(internal)?;
        Ok(())
    }

    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool> {
        let result = sqlx::query("DELETE FROM location_shares WHERE id = $1 AND user_id = $2")
            .bind(id)
            .bind(user_id)
            .execute(&self.pool)
            .await
            .map_err(internal)?;
        Ok(result.rows_affected() > 0)
    }
}
