mod favorites;
mod friendships;
mod location_shares;
mod memories;
mod users;

use bledi_application::AppError;
use bledi_domain::geo::{SearchArea, EARTH_RADIUS_M};
use sqlx::migrate::Migrator;
use sqlx::postgres::PgArguments;
use sqlx::query::QueryAs;
use sqlx::Postgres;

pub use favorites::PostgresFavoriteStore;
pub use friendships::PostgresFriendshipStore;
pub use location_shares::PostgresLocationShareStore;
pub use memories::PostgresMemoryStore;
pub use users::PostgresUserStore;

pub static MIGRATOR: Migrator = sqlx::migrate!("../migrations");

fn internal(e: sqlx::Error) -> AppError {
    AppError::internal(e)
}

fn is_unique_violation(e: &sqlx::Error) -> bool {
    matches!(e, sqlx::Error::Database(db) if db.code().as_deref() == Some("23505"))
}

/// The filter and distance for `bind_area`: an index-friendly box, then the exact haversine
/// on the domain's earth radius. Plain SQL, so the schema needs no extension.
macro_rules! in_area {
    () => {
        "lat BETWEEN $1 AND $2 AND lon BETWEEN $3 AND $4"
    };
}
macro_rules! distance_m {
    () => {
        "2 * $8::float8 * asin(least(1, sqrt(
            power(sin(radians(lat - $5::float8) / 2), 2)
            + cos(radians($5::float8)) * cos(radians(lat)) * power(sin(radians(lon - $6::float8) / 2), 2)
        )))"
    };
}
pub(crate) use {distance_m, in_area};

/// Binds $1 to $9: the box, the centre, the radius ($7), the earth radius and the limit ($9).
fn bind_area<'q, O>(
    query: QueryAs<'q, Postgres, O, PgArguments>,
    area: &SearchArea,
    limit: usize,
) -> QueryAs<'q, Postgres, O, PgArguments> {
    let bounds = area.bounds();
    query
        .bind(bounds.lat_min)
        .bind(bounds.lat_max)
        .bind(bounds.lon_min)
        .bind(bounds.lon_max)
        .bind(area.center.lat())
        .bind(area.center.lon())
        .bind(area.radius_m)
        .bind(EARTH_RADIUS_M)
        .bind(i64::try_from(limit).unwrap_or(i64::MAX))
}
