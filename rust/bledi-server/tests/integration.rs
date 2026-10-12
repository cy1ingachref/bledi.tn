use axum::http::StatusCode;
use bledi_server::ratelimit::RateLimits;
use bledi_server::router;
use bledi_server::state::AppState;
use serde_json::json;
use sqlx::postgres::PgPoolOptions;
use std::net::SocketAddr;

/// A secret long enough for the >= 32 byte rule.
const TEST_JWT_SECRET: &[u8] = b"integration-test-secret-long-enough-0123456789";

/// A namespace unique to this test PROCESS, used to isolate test data.
///
/// `cargo test` runs these tests concurrently against ONE database. Every test
/// calls `setup_db()` at its start, so any destructive cleanup there races: a
/// test that is mid-flight has its users deleted by the next test's setup. That
/// produced a 404 on "cannot friend yourself" (the user lookup found nothing,
/// because the user had just been deleted) and a 500 creating a memory
/// (foreign-key violation against a vanished user) -- neither of which had
/// anything to do with friendships.
///
/// Scoping cleanup to this file was not enough, because every test in the file
/// shares the domain. The fix is to stop deleting altogether and instead give
/// every test run data that cannot collide with anything else. Each process
/// gets a fresh token, so parallel tests cannot see each other's rows and
/// re-running the binary against the same database cannot either.
fn namespace() -> &'static str {
    static NS: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    NS.get_or_init(|| uuid::Uuid::new_v4().simple().to_string()[..12].to_string())
}

/// An email unique to this test process. `name` distinguishes users within it.
fn email_for(name: &str) -> String {
    format!("{name}.{}@itest.invalid", namespace())
}

async fn setup_db() -> AppState {
    let database_url = std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "postgres://postgres:postgres@localhost:5432/bledi".to_string());

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await
        .expect("Failed to connect to database");

    // Run migrations
    sqlx::migrate!()
        .run(&pool)
        .await
        .expect("Failed to run migrations");

    // Deliberately NO cleanup here. See `namespace()`: rows are namespaced per
    // process, so there is nothing to delete and deleting would reintroduce the
    // race. The CI database is an ephemeral container, so leftover rows are
    // free; locally, `DROP DATABASE` is the way to reset.

    // `for_tests()` rather than the production limits: 11 tests registering
    // users from one loopback IP would otherwise trip the 5-per-5-minutes
    // register limit and fail with 429s. The limiter itself is unit-tested.
    AppState::with_limits(
        pool,
        TEST_JWT_SECRET.to_vec(),
        bledi_server::allowed_origins_from_env(),
        RateLimits::for_tests(),
    )
}

async fn spawn_server() -> SocketAddr {
    let state = setup_db().await;

    let app = router(state);

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();

    tokio::spawn(async move {
        axum::serve(
            listener,
            app.into_make_service_with_connect_info::<SocketAddr>(),
        )
        .await
        .unwrap();
    });

    // Wait for server to be ready
    for _ in 0..30 {
        if tokio::net::TcpStream::connect(addr).await.is_ok() {
            break;
        }
        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    }

    addr
}

/// Register a user and return (token, user_id).
async fn register_user(client: &reqwest::Client, base: &str, email: &str) -> (String, String) {
    let res = client
        .post(format!("{base}/api/v1/auth/register"))
        .json(&json!({
            "email": email,
            "password": "test123456",
            "display_name": "Test User"
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(
        res.status(),
        StatusCode::CREATED,
        "registration of {email} should succeed"
    );
    let body: serde_json::Value = res.json().await.unwrap();
    let token = body["token"].as_str().unwrap().to_string();
    let user_id = body["user"]["id"].as_str().unwrap().to_string();
    (token, user_id)
}

#[tokio::test]
async fn test_health() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();

    let res = client
        .get(format!("http://{addr}/api/v1/health"))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::OK);
    let body: serde_json::Value = res.json().await.unwrap();
    assert_eq!(body["status"], "ok");
}

#[tokio::test]
async fn test_register_and_login() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");

    let res = client
        .post(format!("{base}/api/v1/auth/register"))
        .json(&json!({
            "email": email_for("integration"),
            "password": "test123456",
            "display_name": "Integration Test"
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::CREATED);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["token"].as_str().is_some());
    assert_eq!(body["user"]["email"], email_for("integration"));

    // Login
    let res = client
        .post(format!("{base}/api/v1/auth/login"))
        .json(&json!({
            "email": email_for("integration"),
            "password": "test123456"
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::OK);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["token"].as_str().is_some());

    // Login with wrong password
    let res = client
        .post(format!("{base}/api/v1/auth/login"))
        .json(&json!({
            "email": email_for("integration"),
            "password": "wrong"
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_unauthenticated_access_fails() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");

    let res = client
        .get(format!("{base}/api/v1/memories"))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn test_memories_crud() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");

    let (token, _uid) = register_user(&client, &base, &email_for("memory")).await;

    let res = client
        .post(format!("{base}/api/v1/memories"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "lat": 36.8,
            "lon": 10.2,
            "title": "Test memory",
            "description": "Integration test",
            "media_url": "https://example.com/img.jpg",
            "media_type": "image",
            "visibility": "public",
            "unlock_radius_m": 200
        }))
        .send()
        .await
        .unwrap();

    if res.status() != StatusCode::CREATED {
        let status = res.status();
        let body = res.text().await.unwrap();
        panic!("Expected 201, got {}: {}", status, body);
    }
    let body: serde_json::Value = res.json().await.unwrap();
    assert_eq!(body["title"], "Test memory");
    assert_eq!(body["visibility"], "public");

    let res = client
        .get(format!("{base}/api/v1/memories"))
        .header("Authorization", format!("Bearer {token}"))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::OK);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(!body.as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_favorites_crud() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");

    let (token, _uid) = register_user(&client, &base, &email_for("fav")).await;

    let res = client
        .post(format!("{base}/api/v1/favorites"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "kind": "station",
            "ref_id": "test_station",
            "label": "Test Station"
        }))
        .send()
        .await
        .unwrap();

    if res.status() != StatusCode::CREATED {
        let status = res.status();
        let body = res.text().await.unwrap();
        panic!("Expected 201, got {}: {}", status, body);
    }
    let body: serde_json::Value = res.json().await.unwrap();
    assert_eq!(body["kind"], "station");
    assert_eq!(body["label"], "Test Station");
}

#[tokio::test]
async fn test_location_share_requires_expiry() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");

    let (token, _uid) = register_user(&client, &base, &email_for("share")).await;

    // Missing expires_at must be rejected: the README promises shares expire.
    let res = client
        .post(format!("{base}/api/v1/location-shares"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "lat": 36.8,
            "lon": 10.2,
            "accuracy_m": 10.0,
            "note": "Test share",
            "is_active": true
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(
        res.status(),
        StatusCode::BAD_REQUEST,
        "a location share without expires_at must be a 400"
    );

    // An expiry beyond the horizon must also be rejected.
    let far = chrono::Utc::now() + chrono::Duration::hours(48);
    let res = client
        .post(format!("{base}/api/v1/location-shares"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "lat": 36.8, "lon": 10.2, "accuracy_m": 10.0,
            "note": "too long", "is_active": true,
            "expires_at": far.to_rfc3339()
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::BAD_REQUEST);

    // A valid expiry is accepted.
    let soon = chrono::Utc::now() + chrono::Duration::hours(1);
    let res = client
        .post(format!("{base}/api/v1/location-shares"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "lat": 36.8, "lon": 10.2, "accuracy_m": 10.0,
            "note": "Test share", "is_active": true,
            "expires_at": soon.to_rfc3339()
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::CREATED);
    let body: serde_json::Value = res.json().await.unwrap();
    assert_eq!(body["note"], "Test share");
    assert_eq!(body["is_active"], true);
}

#[tokio::test]
async fn test_validation_rejects_out_of_range_coordinates() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");
    let (token, _uid) = register_user(&client, &base, &email_for("validate")).await;

    // Paris is outside Tunisia's bounding box.
    let res = client
        .post(format!("{base}/api/v1/memories"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "lat": 48.8566, "lon": 2.3522,
            "media_url": "https://example.com/img.jpg",
            "media_type": "image", "visibility": "public",
            "unlock_radius_m": 200
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::BAD_REQUEST);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(
        body["error"].as_str().unwrap().contains("lat"),
        "the error should name the offending field: {body}"
    );

    // An out-of-range unlock radius is rejected, not clamped.
    let res = client
        .post(format!("{base}/api/v1/memories"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "lat": 36.8, "lon": 10.2,
            "media_url": "https://example.com/img.jpg",
            "media_type": "image", "visibility": "public",
            "unlock_radius_m": -5
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_nearby_memories_never_return_media_url() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");
    let (token, _uid) = register_user(&client, &base, &email_for("nearby")).await;

    let res = client
        .post(format!("{base}/api/v1/memories"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "lat": 36.8, "lon": 10.2, "title": "Nearby",
            "media_url": "https://example.com/secret.jpg",
            "media_type": "image", "visibility": "public",
            "unlock_radius_m": 200
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::CREATED);

    let res = client
        .get(format!(
            "{base}/api/v1/memories/nearby?lat=36.8&lon=10.2&radius_m=1000"
        ))
        .header("Authorization", format!("Bearer {token}"))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::OK);
    let body: serde_json::Value = res.json().await.unwrap();
    let arr = body.as_array().expect("array");
    assert!(!arr.is_empty(), "the memory just created should be nearby");
    for item in arr {
        assert!(
            item.get("media_url").is_none(),
            "nearby must not expose media_url: {item}"
        );
        assert_eq!(item["locked"], true);
    }

    // An uncapped radius is a 400, not a silently-widened search.
    let res = client
        .get(format!(
            "{base}/api/v1/memories/nearby?lat=36.8&lon=10.2&radius_m=999999"
        ))
        .header("Authorization", format!("Bearer {token}"))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn test_unlock_radius_is_enforced() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");
    let (token, _uid) = register_user(&client, &base, &email_for("unlock")).await;

    let res = client
        .post(format!("{base}/api/v1/memories"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({
            "lat": 36.8000, "lon": 10.1800, "title": "Pinned",
            "media_url": "https://example.com/media.jpg",
            "media_type": "image", "visibility": "public",
            "unlock_radius_m": 200
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::CREATED);
    let created: serde_json::Value = res.json().await.unwrap();
    let id = created["id"].as_str().unwrap();

    // Far away (~1.1 km north): denied, and the body must not carry the media.
    let res = client
        .post(format!("{base}/api/v1/memories/{id}/unlock"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({ "lat": 36.8100, "lon": 10.1800 }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::FORBIDDEN);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(
        body.get("media_url").is_none(),
        "a denied unlock must not leak media_url: {body}"
    );
    assert!(body["distance_m"].as_f64().unwrap() > 200.0);

    // On the pin: allowed, with media.
    let res = client
        .post(format!("{base}/api/v1/memories/{id}/unlock"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({ "lat": 36.8000, "lon": 10.1800 }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::OK);
    let body: serde_json::Value = res.json().await.unwrap();
    assert_eq!(
        body["media_url"].as_str(),
        Some("https://example.com/media.jpg")
    );
    assert_eq!(body["locked"], false);
}

#[tokio::test]
async fn test_friends_only_memory_visibility() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");

    let (owner_token, _owner_id) = register_user(&client, &base, &email_for("owner")).await;
    let (stranger_token, _s) = register_user(&client, &base, &email_for("stranger")).await;
    let (friend_token, _f) = register_user(&client, &base, &email_for("friend")).await;

    // Owner creates a friends-only memory.
    let res = client
        .post(format!("{base}/api/v1/memories"))
        .header("Authorization", format!("Bearer {owner_token}"))
        .json(&json!({
            "lat": 36.8, "lon": 10.2, "title": "Friends only",
            "media_url": "https://example.com/private.jpg",
            "media_type": "image", "visibility": "friends",
            "unlock_radius_m": 200
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::CREATED);
    let created: serde_json::Value = res.json().await.unwrap();
    let id = created["id"].as_str().unwrap();

    // A stranger must NOT be able to read it. This is the bug that made the
    // friends level decorative.
    let res = client
        .get(format!("{base}/api/v1/memories/{id}"))
        .header("Authorization", format!("Bearer {stranger_token}"))
        .send()
        .await
        .unwrap();
    assert_eq!(
        res.status(),
        StatusCode::FORBIDDEN,
        "a stranger must not read a friends-only memory"
    );

    // Establish the friendship: request, then accept.
    let res = client
        .post(format!("{base}/api/v1/friendships/request"))
        .header("Authorization", format!("Bearer {owner_token}"))
        .json(&json!({ "friend_email": email_for("friend") }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::CREATED);

    let res = client
        .post(format!("{base}/api/v1/friendships/accept"))
        .header("Authorization", format!("Bearer {friend_token}"))
        .json(&json!({ "friend_email": email_for("owner") }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::OK);

    // Now the friend can read it.
    let res = client
        .get(format!("{base}/api/v1/memories/{id}"))
        .header("Authorization", format!("Bearer {friend_token}"))
        .send()
        .await
        .unwrap();
    assert_eq!(
        res.status(),
        StatusCode::OK,
        "an accepted friend must be able to read a friends-only memory"
    );

    // The stranger still cannot.
    let res = client
        .get(format!("{base}/api/v1/memories/{id}"))
        .header("Authorization", format!("Bearer {stranger_token}"))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::FORBIDDEN);
}

#[tokio::test]
async fn test_friendship_endpoints() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");

    let (a_token, _a) = register_user(&client, &base, &email_for("alice")).await;
    let (b_token, b_id) = register_user(&client, &base, &email_for("bob")).await;

    // Cannot friend yourself.
    let res = client
        .post(format!("{base}/api/v1/friendships/request"))
        .header("Authorization", format!("Bearer {a_token}"))
        .json(&json!({ "friend_email": email_for("alice") }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::BAD_REQUEST);

    // Unknown user is a 404.
    let res = client
        .post(format!("{base}/api/v1/friendships/request"))
        .header("Authorization", format!("Bearer {a_token}"))
        .json(&json!({ "friend_email": email_for("nobody") }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::NOT_FOUND);

    // Alice requests Bob.
    let res = client
        .post(format!("{base}/api/v1/friendships/request"))
        .header("Authorization", format!("Bearer {a_token}"))
        .json(&json!({ "friend_email": email_for("bob") }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::CREATED);

    // Bob sees it in his incoming requests.
    let res = client
        .get(format!("{base}/api/v1/friendships/requests"))
        .header("Authorization", format!("Bearer {b_token}"))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::OK);
    let body: serde_json::Value = res.json().await.unwrap();
    assert_eq!(body.as_array().unwrap().len(), 1);
    assert_eq!(body[0]["email"], email_for("alice"));

    // Duplicate request is a conflict.
    let res = client
        .post(format!("{base}/api/v1/friendships/request"))
        .header("Authorization", format!("Bearer {a_token}"))
        .json(&json!({ "friend_email": email_for("bob") }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::CONFLICT);

    // Bob accepts.
    let res = client
        .post(format!("{base}/api/v1/friendships/accept"))
        .header("Authorization", format!("Bearer {b_token}"))
        .json(&json!({ "friend_email": email_for("alice") }))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::OK);

    // Both sides now list each other.
    for (tok, other) in [(&a_token, email_for("bob")), (&b_token, email_for("alice"))] {
        let res = client
            .get(format!("{base}/api/v1/friendships"))
            .header("Authorization", format!("Bearer {tok}"))
            .send()
            .await
            .unwrap();
        assert_eq!(res.status(), StatusCode::OK);
        let body: serde_json::Value = res.json().await.unwrap();
        assert_eq!(body.as_array().unwrap().len(), 1);
        assert_eq!(body[0]["email"], other);
        assert_eq!(body[0]["status"], "accepted");
    }

    // Unfriend.
    let res = client
        .delete(format!("{base}/api/v1/friendships/{b_id}"))
        .header("Authorization", format!("Bearer {a_token}"))
        .send()
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::NO_CONTENT);

    let res = client
        .get(format!("{base}/api/v1/friendships"))
        .header("Authorization", format!("Bearer {a_token}"))
        .send()
        .await
        .unwrap();
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body.as_array().unwrap().is_empty());
}
