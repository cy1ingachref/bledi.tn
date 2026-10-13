use async_trait::async_trait;
use bledi_application::ports::{NewUser, Result, StoredUser, UserStore};
use bledi_application::AppError;
use bledi_domain::user::User;
use chrono::{DateTime, Utc};
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

use crate::{internal, is_unique_violation};

#[derive(FromRow)]
struct UserRow {
    id: Uuid,
    email: String,
    display_name: Option<String>,
    created_at: DateTime<Utc>,
    password_hash: String,
}

impl From<UserRow> for StoredUser {
    fn from(row: UserRow) -> Self {
        StoredUser {
            user: User {
                id: row.id,
                email: row.email,
                display_name: row.display_name,
                created_at: row.created_at,
            },
            password_hash: row.password_hash,
        }
    }
}

fn user(row: UserRow) -> User {
    StoredUser::from(row).user
}

#[derive(Clone)]
pub struct PostgresUserStore {
    pool: PgPool,
}

impl PostgresUserStore {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl UserStore for PostgresUserStore {
    async fn insert(&self, new: NewUser) -> Result<User> {
        sqlx::query_as::<_, UserRow>(
            "INSERT INTO users (email, password_hash, display_name) VALUES ($1, $2, $3)
             RETURNING id, email, display_name, created_at, password_hash",
        )
        .bind(new.email)
        .bind(new.password_hash)
        .bind(new.display_name)
        .fetch_one(&self.pool)
        .await
        .map(user)
        .map_err(|e| {
            if is_unique_violation(&e) {
                AppError::EmailTaken
            } else {
                internal(e)
            }
        })
    }

    async fn get(&self, id: Uuid) -> Result<Option<User>> {
        sqlx::query_as::<_, UserRow>(
            "SELECT id, email, display_name, created_at, password_hash FROM users WHERE id = $1",
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await
        .map(|row| row.map(user))
        .map_err(internal)
    }

    async fn get_many(&self, ids: &[Uuid]) -> Result<Vec<User>> {
        sqlx::query_as::<_, UserRow>(
            "SELECT id, email, display_name, created_at, password_hash FROM users WHERE id = ANY($1)",
        )
        .bind(ids)
        .fetch_all(&self.pool)
        .await
        .map(|rows| rows.into_iter().map(user).collect())
        .map_err(internal)
    }

    async fn find_by_email(&self, email: &str) -> Result<Option<StoredUser>> {
        sqlx::query_as::<_, UserRow>(
            "SELECT id, email, display_name, created_at, password_hash FROM users WHERE email = $1",
        )
        .bind(email)
        .fetch_optional(&self.pool)
        .await
        .map(|row| row.map(StoredUser::from))
        .map_err(internal)
    }
}
