mod favorites;
mod friendships;
mod users;

use bledi_application::AppError;
use sqlx::migrate::Migrator;

pub use favorites::PostgresFavoriteStore;
pub use friendships::PostgresFriendshipStore;
pub use users::PostgresUserStore;

pub static MIGRATOR: Migrator = sqlx::migrate!("../migrations");

fn internal(e: sqlx::Error) -> AppError {
    AppError::internal(e)
}

fn is_unique_violation(e: &sqlx::Error) -> bool {
    matches!(e, sqlx::Error::Database(db) if db.code().as_deref() == Some("23505"))
}
