use axum::http::StatusCode;
use bledi_server::router;
use bledi_server::state::AppState;
use serde_json::json;
use sqlx::postgres::PgPoolOptions;
use std::net::SocketAddr;

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

    // Clean up test data
    sqlx::query("DELETE FROM location_shares WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%')")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query(
        "DELETE FROM favorites WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%')",
    )
    .execute(&pool)
    .await
    .unwrap();
    sqlx::query(
        "DELETE FROM memories WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%')",
    )
    .execute(&pool)
    .await
    .unwrap();
    sqlx::query("DELETE FROM friendships WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%test%') OR friend_id IN (SELECT id FROM users WHERE email LIKE '%test%')")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("DELETE FROM users WHERE email LIKE '%test%'")
        .execute(&pool)
        .await
        .unwrap();

    AppState { pool }
}

async fn spawn_server() -> SocketAddr {
    let state = setup_db().await;

    let app = router(state);

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();

    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
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

    // Register
    let res = client
        .post(format!("{base}/api/v1/auth/register"))
        .json(&json!({
            "email": "integration@test.com",
            "password": "test123456",
            "display_name": "Integration Test"
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), StatusCode::CREATED);
    let body: serde_json::Value = res.json().await.unwrap();
    assert!(body["token"].as_str().is_some());
    assert_eq!(body["user"]["email"], "integration@test.com");

    // Login
    let res = client
        .post(format!("{base}/api/v1/auth/login"))
        .json(&json!({
            "email": "integration@test.com",
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
            "email": "integration@test.com",
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

    // Register and get token
    let res = client
        .post(format!("{base}/api/v1/auth/register"))
        .json(&json!({
            "email": "memory@test.com",
            "password": "test123456",
            "display_name": "Memory Test"
        }))
        .send()
        .await
        .unwrap();
    let body: serde_json::Value = res.json().await.unwrap();
    let token = body["token"].as_str().unwrap().to_string();

    // Create memory
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

    // List memories
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

    // Register and get token
    let res = client
        .post(format!("{base}/api/v1/auth/register"))
        .json(&json!({
            "email": "fav@test.com",
            "password": "test123456",
            "display_name": "Fav Test"
        }))
        .send()
        .await
        .unwrap();
    let body: serde_json::Value = res.json().await.unwrap();
    let token = body["token"].as_str().unwrap().to_string();

    // Create favorite
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
async fn test_location_shares() {
    let addr = spawn_server().await;
    let client = reqwest::Client::new();
    let base = format!("http://{addr}");

    // Register and get token
    let res = client
        .post(format!("{base}/api/v1/auth/register"))
        .json(&json!({
            "email": "share@test.com",
            "password": "test123456",
            "display_name": "Share Test"
        }))
        .send()
        .await
        .unwrap();
    let body: serde_json::Value = res.json().await.unwrap();
    let token = body["token"].as_str().unwrap().to_string();

    // Create location share
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

    assert_eq!(res.status(), StatusCode::CREATED);
    let body: serde_json::Value = res.json().await.unwrap();
    assert_eq!(body["note"], "Test share");
    assert_eq!(body["is_active"], true);
}
