use axum::body::Body;
use axum::http::{header, Method, Request, StatusCode};
use serde_json::json;

use crate::support::{email, json_of, TestApp};

#[tokio::test]
async fn health_reports_the_service() {
    let (status, body) = TestApp::new()
        .call(Method::GET, "/health", None, None)
        .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        body,
        json!({ "status": "ok", "service": "bledi-server", "version": "0.1.0" })
    );
}

#[tokio::test]
async fn register_then_login() {
    let app = TestApp::new();
    let register = json!({
        "email": email("integration"), "password": "test123456", "display_name": "Integration"
    });
    let (status, body) = app
        .call(Method::POST, "/auth/register", None, Some(register.clone()))
        .await;
    assert_eq!(status, StatusCode::CREATED);
    assert!(body["token"].is_string());
    assert_eq!(body["user"]["email"], email("integration"));
    assert!(body["user"].get("password_hash").is_none());

    let (status, body) = app
        .call(Method::POST, "/auth/register", None, Some(register))
        .await;
    assert_eq!(status, StatusCode::CONFLICT);
    assert_eq!(body["code"], "email_taken");

    let login = |password: &str| json!({ "email": email("integration"), "password": password });
    let (status, body) = app
        .call(Method::POST, "/auth/login", None, Some(login("test123456")))
        .await;
    assert_eq!(status, StatusCode::OK);
    let token = body["token"].as_str().unwrap();

    let (status, body) = app
        .call(Method::POST, "/auth/login", None, Some(login("wrong")))
        .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(
        body,
        json!({ "error": "Invalid credentials", "code": "invalid_credentials" })
    );

    let (status, body) = app.get("/users/me", token).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["display_name"], "Integration");
}

#[tokio::test]
async fn protected_routes_need_a_bearer_token() {
    let app = TestApp::new();
    let (token, _) = app.register("auth").await;

    let (status, body) = app.call(Method::GET, "/memories", None, None).await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body["code"], "unauthorized");

    for authorization in ["Basic abc", "Bearer", "Bearer   ", "token"] {
        let request = Request::get("/api/v1/memories")
            .header(header::AUTHORIZATION, authorization)
            .body(Body::empty())
            .unwrap();
        let (status, _) = json_of(app.send(request).await).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED, "{authorization:?}");
    }

    let (status, _) = app.get("/memories", "not-a-token").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);

    let request = Request::get("/api/v1/memories")
        .header(header::AUTHORIZATION, format!("bearer {token}"))
        .body(Body::empty())
        .unwrap();
    let (status, _) = json_of(app.send(request).await).await;
    assert_eq!(status, StatusCode::OK, "the scheme is case insensitive");
}

#[tokio::test]
async fn a_malformed_body_gets_a_json_error() {
    let app = TestApp::new();
    let request = Request::post("/api/v1/auth/login")
        .header(header::CONTENT_TYPE, "application/json")
        .body(Body::from("{not json"))
        .unwrap();
    let (status, body) = json_of(app.send(request).await).await;
    assert!(status.is_client_error());
    assert_eq!(body["code"], "invalid_request");
    assert!(body["error"].is_string());
}
