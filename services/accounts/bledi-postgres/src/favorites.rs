use async_trait::async_trait;
use bledi_application::ports::{FavoriteStore, NewFavorite, Result};
use bledi_domain::favorite::{Favorite, FavoriteKind};
use chrono::{DateTime, Utc};
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

use crate::internal;
#[derive(FromRow)]
struct FavoriteRow {
    id: Uuid,
    user_id: Uuid,
    #[sqlx(try_from = "String")]
    kind: FavoriteKind,
    ref_id: String,
    label: Option<String>,
    created_at: DateTime<Utc>,
}

impl From<FavoriteRow> for Favorite {
    fn from(row: FavoriteRow) -> Self {
        Favorite {
            id: row.id,
            user_id: row.user_id,
            kind: row.kind,
            ref_id: row.ref_id,
            label: row.label,
            created_at: row.created_at,
        }
    }
}

#[derive(Clone)]
pub struct PostgresFavoriteStore {
    pool: PgPool,
}

impl PostgresFavoriteStore {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl FavoriteStore for PostgresFavoriteStore {
    async fn owned_by(&self, user_id: Uuid) -> Result<Vec<Favorite>> {
        sqlx::query_as::<_, FavoriteRow>(
            "SELECT id, user_id, kind::text AS kind, ref_id, label, created_at
             FROM favorites WHERE user_id = $1 ORDER BY created_at DESC",
        )
        .bind(user_id)
        .fetch_all(&self.pool)
        .await
        .map(|rows| rows.into_iter().map(Favorite::from).collect())
        .map_err(internal)
    }

    async fn owned_by_paginated(
        &self,
        user_id: Uuid,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<Favorite>> {
        sqlx::query_as::<_, FavoriteRow>(
            "SELECT id, user_id, kind::text AS kind, ref_id, label, created_at
             FROM favorites
             WHERE user_id = $1
             ORDER BY created_at DESC
             LIMIT $2 OFFSET $3",
        )
        .bind(user_id)
        .bind(limit as i64)
        .bind(offset as i64)
        .fetch_all(&self.pool)
        .await
        .map(|rows| rows.into_iter().map(Favorite::from).collect())
        .map_err(internal)
    }

    async fn upsert(&self, new: NewFavorite) -> Result<Favorite> {
        sqlx::query_as::<_, FavoriteRow>(
            "INSERT INTO favorites (user_id, kind, ref_id, label) VALUES ($1, $2::favorite_kind, $3, $4)
             ON CONFLICT (user_id, kind, ref_id) DO UPDATE SET label = EXCLUDED.label
             RETURNING id, user_id, kind::text AS kind, ref_id, label, created_at",
        )
        .bind(new.user_id)
        .bind(new.kind.as_str())
        .bind(new.ref_id)
        .bind(new.label)
        .fetch_one(&self.pool)
        .await
        .map(Favorite::from)
        .map_err(internal)
    }

    async fn delete(&self, id: Uuid, user_id: Uuid) -> Result<bool> {
        let result = sqlx::query("DELETE FROM favorites WHERE id = $1 AND user_id = $2")
            .bind(id)
            .bind(user_id)
            .execute(&self.pool)
            .await
            .map_err(internal)?;
        Ok(result.rows_affected() > 0)
    }
}
