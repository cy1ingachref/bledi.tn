use axum::http::{Method, StatusCode};
use chrono::{Duration, Utc};
use serde_json::{json, Value};

use crate::support::{email, TestApp};

#[tokio::test]
async fn saving_a_favorite_twice_keeps_one() {
    let app = TestApp::new();
    let (token, _) = app.register("fav").await;
    let favorite =
        |label: &str| json!({ "kind": "station", "ref_id": "test_station", "label": label });

    let (status, first) = app.post("/favorites", &token, favorite("Home")).await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(first["kind"], "station");
    assert_eq!(first["label"], "Home");
    let (_, second) = app.post("/favorites", &token, favorite("Work")).await;
    assert_eq!(second["id"], first["id"]);

    let (status, list) = app.get("/favorites", &token).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(list, json!([second]));

    let path = format!("/favorites/{}", first["id"].as_str().unwrap());
    let (status, _) = app.call(Method::DELETE, &path, Some(&token), None).await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    let (status, _) = app.call(Method::DELETE, &path, Some(&token), None).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

fn share(expires_at: Option<String>) -> Value {
    json!({
        "lat": 36.8, "lon": 10.2, "accuracy_m": 10.0,
        "note": "Test share", "is_active": true, "expires_at": expires_at
    })
}

#[tokio::test]
async fn location_shares_must_expire_within_a_day() {
    let app = TestApp::new();
    let (token, _) = app.register("share").await;

    let (status, body) = app.post("/location-shares", &token, share(None)).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["code"], "invalid_expiry");
    let far = (Utc::now() + Duration::hours(48)).to_rfc3339();
    let (status, _) = app.post("/location-shares", &token, share(Some(far))).await;
    assert_eq!(status, StatusCode::BAD_REQUEST);

    let soon = (Utc::now() + Duration::hours(1)).to_rfc3339();
    let (status, body) = app
        .post("/location-shares", &token, share(Some(soon)))
        .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(body["note"], "Test share");
    assert_eq!(body["is_active"], true);
}

#[tokio::test]
async fn nearby_shares_come_from_friends_only() {
    let app = TestApp::new();
    let (alice, _) = app.register("alice").await;
    let (bob, _) = app.register("bob").await;
    let (stranger, _) = app.register("stranger").await;
    let soon = || Some((Utc::now() + Duration::hours(1)).to_rfc3339());
    for token in [&bob, &stranger] {
        let (status, _) = app.post("/location-shares", token, share(soon())).await;
        assert_eq!(status, StatusCode::CREATED);
    }
    app.befriend((&alice, "alice"), (&bob, "bob")).await;

    let (status, body) = app
        .get(
            "/location-shares/nearby?lat=36.8&lon=10.2&radius_m=1000",
            &alice,
        )
        .await;
    assert_eq!(status, StatusCode::OK);
    let found = body.as_array().unwrap();
    assert_eq!(found.len(), 1);
    let (_, mine) = app.get("/location-shares", &bob).await;
    assert_eq!(found[0]["id"], mine[0]["id"]);
}

#[tokio::test]
async fn friendship_lifecycle() {
    let app = TestApp::new();
    let (alice, _) = app.register("alice").await;
    let (bob, bob_id) = app.register("bob").await;
    let request = |to: &str| json!({ "friend_email": email(to) });

    let (status, body) = app
        .post("/friendships/request", &alice, request("alice"))
        .await;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    assert_eq!(body["code"], "self_friend_request");
    let (status, _) = app
        .post("/friendships/request", &alice, request("nobody"))
        .await;
    assert_eq!(status, StatusCode::NOT_FOUND);

    let (status, body) = app
        .post("/friendships/request", &alice, request("bob"))
        .await;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(
        body,
        json!({ "status": "pending", "user_id": bob_id, "email": email("bob") })
    );
    let (status, body) = app
        .post("/friendships/request", &alice, request("bob"))
        .await;
    assert_eq!(status, StatusCode::CONFLICT);
    assert_eq!(body["code"], "request_pending");

    let (status, body) = app.get("/friendships/requests", &bob).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body.as_array().unwrap().len(), 1);
    assert_eq!(body[0]["email"], email("alice"));

    let (status, body) = app
        .post("/friendships/accept", &bob, request("alice"))
        .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "accepted");
    let (status, _) = app
        .post("/friendships/accept", &bob, request("alice"))
        .await;
    assert_eq!(status, StatusCode::NOT_FOUND);
    let (status, _) = app
        .post("/friendships/request", &bob, request("alice"))
        .await;
    assert_eq!(status, StatusCode::CONFLICT);

    for (token, other) in [(&alice, "bob"), (&bob, "alice")] {
        let (status, body) = app.get("/friendships", token).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body.as_array().unwrap().len(), 1);
        assert_eq!(body[0]["email"], email(other));
        assert_eq!(body[0]["status"], "accepted");
    }

    let path = format!("/friendships/{bob_id}");
    let (status, _) = app.call(Method::DELETE, &path, Some(&alice), None).await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    let (_, body) = app.get("/friendships", &alice).await;
    assert_eq!(body, json!([]));
    let (status, _) = app.call(Method::DELETE, &path, Some(&alice), None).await;
    assert_eq!(status, StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn crossed_requests_become_a_friendship() {
    let app = TestApp::new();
    let (alice, _) = app.register("alice").await;
    let (bob, _) = app.register("bob").await;
    let (status, _) = app
        .post(
            "/friendships/request",
            &alice,
            json!({ "friend_email": email("bob") }),
        )
        .await;
    assert_eq!(status, StatusCode::CREATED);

    let (status, body) = app
        .post(
            "/friendships/request",
            &bob,
            json!({ "friend_email": email("alice") }),
        )
        .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "accepted");
}
