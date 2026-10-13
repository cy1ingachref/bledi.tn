use axum::http::{Method, StatusCode};
use serde_json::json;

use crate::support::TestApp;

#[tokio::test]
async fn memories_crud() {
    let app = TestApp::new();
    let (token, _) = app.register("memory").await;
    let created = app
        .create_memory(&token, json!({ "title": "Test memory" }))
        .await;
    assert_eq!(created["title"], "Test memory");
    assert_eq!(created["visibility"], "public");
    assert_eq!(created["locked"], false);
    let path = format!("/memories/{}", created["id"].as_str().unwrap());

    let (status, list) = app.get("/memories", &token).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(list, json!([created]));

    let change = json!({ "title": "Renamed", "visibility": "private", "unlock_radius_m": 300 });
    let (status, updated) = app
        .call(Method::PUT, &path, Some(&token), Some(change))
        .await;
    assert_eq!(status, StatusCode::OK, "{updated}");
    assert_eq!(updated["title"], "Renamed");
    assert_eq!(updated["unlock_radius_m"], 300.0);

    let (status, _) = app.call(Method::DELETE, &path, Some(&token), None).await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    let (status, body) = app.get(&path, &token).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    assert_eq!(body["code"], "not_found");
}

#[tokio::test]
async fn coordinates_and_radii_are_validated() {
    let app = TestApp::new();
    let (token, _) = app.register("validate").await;
    let memory = |lat: f64, lon: f64, radius: f64| {
        json!({
            "lat": lat, "lon": lon, "media_url": "https://example.com/img.jpg",
            "media_type": "image", "visibility": "public", "unlock_radius_m": radius
        })
    };

    let (status, body) = app
        .post("/memories", &token, memory(48.8566, 2.3522, 200.0))
        .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert!(body["error"].as_str().unwrap().contains("lat"), "{body}");
    assert_eq!(body["code"], "invalid_coordinates");

    let (status, body) = app
        .post("/memories", &token, memory(36.8, 10.2, -5.0))
        .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["code"], "invalid_radius");

    let (status, body) = app
        .get("/memories/nearby?lat=36.8&lon=10.2&radius_m=999999", &token)
        .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["code"], "invalid_radius");

    let (status, body) = app.get("/memories/nearby?lat=abc&lon=10.2", &token).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["code"], "invalid_request");
}

#[tokio::test]
async fn nearby_never_returns_media_url() {
    let app = TestApp::new();
    let (token, _) = app.register("nearby").await;
    app.create_memory(
        &token,
        json!({ "media_url": "https://example.com/secret.jpg" }),
    )
    .await;

    let (status, body) = app
        .get("/memories/nearby?lat=36.8&lon=10.18&radius_m=1000", &token)
        .await;
    assert_eq!(status, StatusCode::OK);
    let found = body.as_array().unwrap();
    assert_eq!(found.len(), 1);
    assert!(found[0].get("media_url").is_none(), "{body}");
    assert_eq!(found[0]["locked"], true);
}

#[tokio::test]
async fn unlock_enforces_the_radius() {
    let app = TestApp::new();
    let (token, _) = app.register("unlock").await;
    let created = app.create_memory(&token, json!({})).await;
    let path = format!("/memories/{}/unlock", created["id"].as_str().unwrap());

    let (status, body) = app
        .post(&path, &token, json!({ "lat": 36.81, "lon": 10.18 }))
        .await;
    assert_eq!(status, StatusCode::FORBIDDEN);
    assert!(body.get("media_url").is_none(), "{body}");
    assert_eq!(body["code"], "too_far");
    assert_eq!(body["unlock_radius_m"], 200.0);
    let distance = body["distance_m"].as_f64().unwrap();
    assert!((1100.0..1125.0).contains(&distance), "{distance}");

    let (status, body) = app
        .post(&path, &token, json!({ "lat": 36.8, "lon": 10.18 }))
        .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["media_url"], "https://example.com/media.jpg");
    assert_eq!(body["locked"], false);
    assert_eq!(body["distance_m"], 0.0);
}

#[tokio::test]
async fn friends_only_memories_need_an_accepted_friendship() {
    let app = TestApp::new();
    let (owner, _) = app.register("owner").await;
    let (stranger, _) = app.register("stranger").await;
    let (friend, _) = app.register("friend").await;
    let created = app
        .create_memory(&owner, json!({ "visibility": "friends" }))
        .await;
    let path = format!("/memories/{}", created["id"].as_str().unwrap());

    let (status, body) = app.get(&path, &stranger).await;
    assert_eq!(status, StatusCode::FORBIDDEN);
    assert_eq!(body["code"], "forbidden");
    let unlock = format!("{path}/unlock");
    let (status, body) = app
        .post(&unlock, &stranger, json!({ "lat": 36.8, "lon": 10.18 }))
        .await;
    assert_eq!(
        status,
        StatusCode::FORBIDDEN,
        "on the pin, but not a friend"
    );
    assert!(body.get("media_url").is_none());

    app.befriend((&owner, "owner"), (&friend, "friend")).await;
    let (status, _) = app.get(&path, &friend).await;
    assert_eq!(status, StatusCode::OK);
    let (status, _) = app.get(&path, &stranger).await;
    assert_eq!(status, StatusCode::FORBIDDEN);
}
