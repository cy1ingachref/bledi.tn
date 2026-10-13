use std::time::Duration;

use axum::body::Body;
use axum::http::{header, Method, Request, StatusCode};
use bledi_http::rate_limit::Limit;
use serde_json::json;

use crate::support::{config, email, json_of, TestApp};

fn login_from(forwarded_for: &str) -> Request<Body> {
    Request::post("/api/v1/auth/login")
        .header(header::CONTENT_TYPE, "application/json")
        .header("x-forwarded-for", forwarded_for)
        .body(Body::from(
            json!({ "email": email("nobody"), "password": "whatever1" }).to_string(),
        ))
        .unwrap()
}

#[tokio::test]
async fn login_is_rate_limited_per_client() {
    let mut config = config();
    config.rate_limits.login = Limit::new(2, Duration::from_secs(60));
    let app = TestApp::with(config);

    for _ in 0..2 {
        let response = app.send(login_from("203.0.113.1")).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }
    let response = app.send(login_from("203.0.113.2")).await;
    assert_eq!(
        response.status(),
        StatusCode::TOO_MANY_REQUESTS,
        "the forwarded address is not trusted, so every caller shares one bucket"
    );
    assert!(response.headers().contains_key(header::RETRY_AFTER));
    let (_, body) = json_of(response).await;
    assert_eq!(body["code"], "rate_limited");
    assert!(body["retry_after_secs"].as_u64().unwrap() >= 1);
}

#[tokio::test]
async fn a_trusted_proxy_header_splits_the_buckets() {
    let mut config = config();
    config.rate_limits.login = Limit::new(1, Duration::from_secs(60));
    config.trust_proxy_headers = true;
    let app = TestApp::with(config);

    let response = app.send(login_from("203.0.113.1")).await;
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    let response = app.send(login_from("203.0.113.2, 10.0.0.1")).await;
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    let response = app.send(login_from("203.0.113.1")).await;
    assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
}

#[tokio::test]
async fn unlock_is_rate_limited_per_user() {
    let mut config = config();
    config.rate_limits.unlock = Limit::new(1, Duration::from_secs(60));
    let app = TestApp::with(config);
    let (token, _) = app.register("unlocker").await;
    let (other, _) = app.register("other").await;
    let created = app.create_memory(&token, json!({})).await;
    let path = format!("/memories/{}/unlock", created["id"].as_str().unwrap());
    let here = json!({ "lat": 36.8, "lon": 10.18 });

    let (status, _) = app.post(&path, &token, here.clone()).await;
    assert_eq!(status, StatusCode::OK);
    let (status, _) = app.post(&path, &token, here.clone()).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);
    let (status, _) = app.post(&path, &other, here).await;
    assert_eq!(status, StatusCode::OK);
}

fn preflight(origin: &str) -> Request<Body> {
    Request::builder()
        .method(Method::OPTIONS)
        .uri("/api/v1/memories")
        .header(header::ORIGIN, origin)
        .header(header::ACCESS_CONTROL_REQUEST_METHOD, "POST")
        .header(header::ACCESS_CONTROL_REQUEST_HEADERS, "authorization")
        .body(Body::empty())
        .unwrap()
}

#[tokio::test]
async fn cors_allows_only_the_configured_origins() {
    let app = TestApp::new();
    let allowed = app.send(preflight("http://localhost:5173")).await;
    let headers = allowed.headers();
    assert_eq!(
        headers[header::ACCESS_CONTROL_ALLOW_ORIGIN],
        "http://localhost:5173"
    );
    assert!(!headers.contains_key(header::ACCESS_CONTROL_ALLOW_CREDENTIALS));

    let refused = app.send(preflight("https://evil.example")).await;
    assert!(!refused
        .headers()
        .contains_key(header::ACCESS_CONTROL_ALLOW_ORIGIN));
}
