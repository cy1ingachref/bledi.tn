//! Runs against the database in DATABASE_URL. Tests share it and run in parallel, so every
//! row they create belongs to users with fresh emails and nothing is ever cleaned up.

use bledi_application::ports::*;
use bledi_application::AppError;
use bledi_domain::favorite::FavoriteKind;
use bledi_domain::friendship::FriendshipStatus;
use bledi_domain::geo::{Coordinates, SearchArea, UnlockRadius};
use bledi_domain::memory::{MediaType, Visibility};
use bledi_postgres::*;
use chrono::{Duration, Utc};
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

async fn pool() -> PgPool {
    let url = std::env::var("DATABASE_URL").expect("DATABASE_URL must point at a test database");
    let pool = PgPoolOptions::new()
        .max_connections(2)
        .connect(&url)
        .await
        .expect("connect");
    MIGRATOR.run(&pool).await.expect("migrate");
    pool
}

async fn user(pool: &PgPool) -> Uuid {
    PostgresUserStore::new(pool.clone())
        .insert(NewUser {
            email: format!("{}@itest.invalid", Uuid::new_v4().simple()),
            password_hash: "hash".into(),
            display_name: None,
        })
        .await
        .unwrap()
        .id
}

fn point(lat: f64, lon: f64) -> Coordinates {
    Coordinates::in_tunisia(lat, lon).unwrap()
}

fn area(lat: f64, lon: f64, radius_m: f64) -> SearchArea {
    SearchArea::new(point(lat, lon), Some(radius_m)).unwrap()
}

fn memory(owner: Uuid, at: Coordinates, visibility: Visibility) -> NewMemory {
    NewMemory {
        user_id: owner,
        location: at,
        title: Some("t".into()),
        description: None,
        media_url: "https://example.com/m.jpg".into(),
        media_key: None,
        media_type: MediaType::Image,
        visibility,
        unlock_radius: UnlockRadius::new(200.0).unwrap(),
    }
}

#[tokio::test]
async fn users_are_unique_by_email_and_found_with_their_hash() {
    let store = PostgresUserStore::new(pool().await);
    let email = format!("{}@itest.invalid", Uuid::new_v4().simple());
    let new = || NewUser {
        email: email.clone(),
        password_hash: "hash".into(),
        display_name: Some("Name".into()),
    };
    let created = store.insert(new()).await.unwrap();
    assert!(matches!(
        store.insert(new()).await,
        Err(AppError::EmailTaken)
    ));

    let found = store.find_by_email(&email).await.unwrap().unwrap();
    assert_eq!(found.user, created);
    assert_eq!(found.password_hash, "hash");
    assert_eq!(store.get(created.id).await.unwrap(), Some(created.clone()));
    assert_eq!(
        store.get_many(&[created.id, Uuid::new_v4()]).await.unwrap(),
        vec![created]
    );
}

#[tokio::test]
async fn memories_round_trip_and_only_the_owner_deletes() {
    let pool = pool().await;
    let store = PostgresMemoryStore::new(pool.clone());
    let owner = user(&pool).await;
    let mut created = store
        .insert(memory(owner, point(36.8, 10.18), Visibility::Friends))
        .await
        .unwrap();
    assert_eq!(created.visibility, Visibility::Friends);
    assert_eq!(store.get(created.id).await.unwrap(), Some(created.clone()));

    created.title = Some("new".into());
    created.visibility = Visibility::Private;
    created.unlock_radius_m = 500.0;
    created.updated_at = Utc::now();
    store.update(&created).await.unwrap();
    let stored = store.get(created.id).await.unwrap().unwrap();
    assert_eq!(stored.title.as_deref(), Some("new"));
    assert_eq!(stored.visibility, Visibility::Private);
    assert_eq!(stored.unlock_radius_m, 500.0);
    assert_eq!(store.owned_by(owner).await.unwrap(), vec![stored]);

    assert!(!store.delete(created.id, user(&pool).await).await.unwrap());
    assert!(store.delete(created.id, owner).await.unwrap());
    assert!(store.get(created.id).await.unwrap().is_none());
}

#[tokio::test]
async fn nearby_memories_respect_visibility_and_distance() {
    let pool = pool().await;
    let store = PostgresMemoryStore::new(pool.clone());
    let (owner, friend, viewer) = (user(&pool).await, user(&pool).await, user(&pool).await);
    let (lat, lon) = (33.9, 9.5);
    let public_far = store
        .insert(memory(owner, point(lat + 0.009, lon), Visibility::Public))
        .await
        .unwrap();
    let public_near = store
        .insert(memory(owner, point(lat, lon), Visibility::Public))
        .await
        .unwrap();
    let friends_only = store
        .insert(memory(owner, point(lat, lon), Visibility::Friends))
        .await
        .unwrap();
    let private = store
        .insert(memory(owner, point(lat, lon), Visibility::Private))
        .await
        .unwrap();
    store
        .insert(memory(owner, point(lat + 0.05, lon), Visibility::Public))
        .await
        .unwrap();

    // Earlier runs leave rows at the same spot, so only this owner's count.
    let ids = |found: Vec<bledi_domain::memory::Memory>| -> Vec<Uuid> {
        found
            .into_iter()
            .filter(|m| m.user_id == owner)
            .map(|m| m.id)
            .collect()
    };
    let here = area(lat, lon, 1500.0);
    let stranger = store.nearby(viewer, &[], &here, 200).await.unwrap();
    assert_eq!(ids(stranger), vec![public_near.id, public_far.id]);

    let as_friend = ids(store.nearby(friend, &[owner], &here, 200).await.unwrap());
    assert_eq!(as_friend.len(), 3);
    assert!(as_friend.contains(&friends_only.id));
    assert_eq!(as_friend.last(), Some(&public_far.id));

    let as_owner = ids(store.nearby(owner, &[], &here, 200).await.unwrap());
    assert_eq!(as_owner.len(), 4);
    assert!(as_owner.contains(&private.id));

    let tight = area(lat, lon, 500.0);
    assert_eq!(
        ids(store.nearby(viewer, &[], &tight, 200).await.unwrap()),
        vec![public_near.id]
    );
    assert_eq!(store.nearby(owner, &[], &here, 1).await.unwrap().len(), 1);
}

#[tokio::test]
async fn friend_requests_are_directed_and_accepted_once() {
    let pool = pool().await;
    let store = PostgresFriendshipStore::new(pool.clone());
    let (a, b) = (user(&pool).await, user(&pool).await);

    store.request(a, b).await.unwrap();
    assert!(matches!(
        store.request(a, b).await,
        Err(AppError::RequestPending)
    ));
    let between = store.between(b, a).await.unwrap();
    assert_eq!(between.len(), 1);
    assert_eq!(
        (between[0].user_id, between[0].status),
        (a, FriendshipStatus::Pending)
    );

    assert!(
        !store.accept(b, a).await.unwrap(),
        "only the recipient accepts"
    );
    assert!(store.accept(a, b).await.unwrap());
    assert!(!store.accept(a, b).await.unwrap(), "already accepted");
    assert_eq!(
        store.of(b).await.unwrap()[0].status,
        FriendshipStatus::Accepted
    );

    assert!(store.remove(b, a).await.unwrap());
    assert!(store.of(a).await.unwrap().is_empty());
    assert!(!store.remove(a, b).await.unwrap());
}

#[tokio::test]
async fn saving_a_favorite_twice_updates_its_label() {
    let pool = pool().await;
    let store = PostgresFavoriteStore::new(pool.clone());
    let owner = user(&pool).await;
    let save = |label: &str| NewFavorite {
        user_id: owner,
        kind: FavoriteKind::Station,
        ref_id: "test_station".into(),
        label: Some(label.into()),
    };
    let first = store.upsert(save("Home")).await.unwrap();
    let second = store.upsert(save("Work")).await.unwrap();
    assert_eq!(second.id, first.id);
    assert_eq!(second.kind, FavoriteKind::Station);
    assert_eq!(store.owned_by(owner).await.unwrap(), vec![second.clone()]);
    assert!(!store.delete(second.id, user(&pool).await).await.unwrap());
    assert!(store.delete(second.id, owner).await.unwrap());
}

#[tokio::test]
async fn nearby_shares_are_live_shares_of_the_given_owners() {
    let pool = pool().await;
    let store = PostgresLocationShareStore::new(pool.clone());
    let (friend, stranger) = (user(&pool).await, user(&pool).await);
    let now = Utc::now();
    let (lat, lon) = (31.5, 9.0);
    let share = |owner: Uuid, is_active: bool, expires_in: Duration| NewLocationShare {
        user_id: owner,
        location: point(lat, lon),
        accuracy_m: Some(10.0),
        note: Some("here".into()),
        is_active,
        expires_at: now + expires_in,
    };
    let live = store
        .insert(share(friend, true, Duration::hours(1)))
        .await
        .unwrap();
    store
        .insert(share(friend, false, Duration::hours(1)))
        .await
        .unwrap();
    store
        .insert(share(friend, true, Duration::minutes(1)))
        .await
        .unwrap();
    store
        .insert(share(stranger, true, Duration::hours(1)))
        .await
        .unwrap();

    let later = now + Duration::minutes(5);
    let found = store
        .nearby(&[friend], &area(lat, lon, 1000.0), later, 100)
        .await
        .unwrap();
    assert_eq!(found, vec![live.clone()]);

    let mut moved = live.clone();
    moved.lat += 0.1;
    moved.updated_at = Utc::now();
    store.update(&moved).await.unwrap();
    assert_eq!(store.get(live.id).await.unwrap().unwrap().lat, moved.lat);
    assert!(store
        .nearby(&[friend], &area(lat, lon, 1000.0), later, 100)
        .await
        .unwrap()
        .is_empty());
    assert_eq!(store.owned_by(friend).await.unwrap()[0].id, live.id);
    assert!(store.delete(live.id, friend).await.unwrap());
}
