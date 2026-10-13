use async_trait::async_trait;
use bledi_application::ports::{FriendshipStore, Result};
use bledi_application::AppError;
use bledi_domain::friendship::{Friendship, FriendshipStatus};
use chrono::{DateTime, Utc};
use sqlx::postgres::PgArguments;
use sqlx::query::QueryAs;
use sqlx::{FromRow, PgPool, Postgres};
use uuid::Uuid;

use crate::{internal, is_unique_violation};

#[derive(FromRow)]
struct FriendshipRow {
    user_id: Uuid,
    friend_id: Uuid,
    #[sqlx(try_from = "String")]
    status: FriendshipStatus,
    created_at: DateTime<Utc>,
}

impl From<FriendshipRow> for Friendship {
    fn from(row: FriendshipRow) -> Self {
        Friendship {
            user_id: row.user_id,
            friend_id: row.friend_id,
            status: row.status,
            created_at: row.created_at,
        }
    }
}

#[derive(Clone)]
pub struct PostgresFriendshipStore {
    pool: PgPool,
}

impl PostgresFriendshipStore {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    async fn fetch(
        &self,
        query: QueryAs<'_, Postgres, FriendshipRow, PgArguments>,
    ) -> Result<Vec<Friendship>> {
        query
            .fetch_all(&self.pool)
            .await
            .map(|rows| rows.into_iter().map(Friendship::from).collect())
            .map_err(internal)
    }
}

#[async_trait]
impl FriendshipStore for PostgresFriendshipStore {
    async fn between(&self, a: Uuid, b: Uuid) -> Result<Vec<Friendship>> {
        let query = sqlx::query_as(
            "SELECT user_id, friend_id, status, created_at FROM friendships
             WHERE (user_id = $1 AND friend_id = $2) OR (user_id = $2 AND friend_id = $1)",
        );
        self.fetch(query.bind(a).bind(b)).await
    }

    async fn of(&self, user_id: Uuid) -> Result<Vec<Friendship>> {
        let query = sqlx::query_as(
            "SELECT user_id, friend_id, status, created_at FROM friendships
             WHERE user_id = $1 OR friend_id = $1",
        );
        self.fetch(query.bind(user_id)).await
    }

    async fn request(&self, from: Uuid, to: Uuid) -> Result<()> {
        sqlx::query(
            "INSERT INTO friendships (user_id, friend_id, status) VALUES ($1, $2, 'pending')",
        )
        .bind(from)
        .bind(to)
        .execute(&self.pool)
        .await
        .map_err(|e| {
            if is_unique_violation(&e) {
                AppError::RequestPending
            } else {
                internal(e)
            }
        })?;
        Ok(())
    }

    async fn accept(&self, requester: Uuid, recipient: Uuid) -> Result<bool> {
        let result = sqlx::query(
            "UPDATE friendships SET status = 'accepted'
             WHERE user_id = $1 AND friend_id = $2 AND status = 'pending'",
        )
        .bind(requester)
        .bind(recipient)
        .execute(&self.pool)
        .await
        .map_err(internal)?;
        Ok(result.rows_affected() > 0)
    }

    async fn remove(&self, a: Uuid, b: Uuid) -> Result<bool> {
        let result = sqlx::query(
            "DELETE FROM friendships
             WHERE (user_id = $1 AND friend_id = $2) OR (user_id = $2 AND friend_id = $1)",
        )
        .bind(a)
        .bind(b)
        .execute(&self.pool)
        .await
        .map_err(internal)?;
        Ok(result.rows_affected() > 0)
    }
}
