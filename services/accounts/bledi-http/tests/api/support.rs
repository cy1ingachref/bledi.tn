use std::path::PathBuf;
use std::time::Duration;

use axum::body::Body;
use axum::http::{header, Method, Request, Response, StatusCode};
use axum::Router;
use bledi_application::testing::Fakes;
use bledi_application::Services;
use bledi_http::cors::{parse_allowed_origins, DEFAULT_ALLOWED_ORIGINS};
use bledi_http::media::MediaStore;
use bledi_http::rate_limit::{Limit, RateLimits};
use bledi_http::{router, HttpConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;
use uuid::Uuid;

pub const UNLIMITED: Limit = Limit::new(u32::MAX, Duration::from_secs(1));

/// A fresh directory per test app, so two tests never see each other's photos.
fn temp_media_root() -> PathBuf {
    std::env::temp_dir().join(format!("bledi-http-test-{}", Uuid::new_v4()))
}

pub fn config() -> HttpConfig {
    HttpConfig {
        allowed_origins: parse_allowed_origins(&DEFAULT_ALLOWED_ORIGINS.join(",")).unwrap(),
        rate_limits: RateLimits {
            login: UNLIMITED,
            register: UNLIMITED,
            unlock: UNLIMITED,
        },
        trust_proxy_headers: false,
        media: MediaStore::new(temp_media_root()).unwrap(),
    }
}

pub struct TestApp {
    router: Router,
}

impl TestApp {
    pub fn new() -> Self {
        Self::with(config())
    }

    pub fn with(config: HttpConfig) -> Self {
        let fakes = Fakes::new();
        Self {
            router: router(Services::new(&fakes.ports()), config),
        }
    }

    pub async fn send(&self, request: Request<Body>) -> Response<Body> {
        self.router.clone().oneshot(request).await.unwrap()
    }

    pub async fn call(
        &self,
        method: Method,
        path: &str,
        token: Option<&str>,
        body: Option<Value>,
    ) -> (StatusCode, Value) {
        let mut request = Request::builder()
            .method(method)
            .uri(format!("/api/v1{path}"));
        if let Some(token) = token {
            request = request.header(header::AUTHORIZATION, format!("Bearer {token}"));
        }
        let request = match body {
            Some(body) => request
                .header(header::CONTENT_TYPE, "application/json")
                .body(Body::from(body.to_string())),
            None => request.body(Body::empty()),
        };
        json_of(self.send(request.unwrap()).await).await
    }

    pub async fn get(&self, path: &str, token: &str) -> (StatusCode, Value) {
        self.call(Method::GET, path, Some(token), None).await
    }

    pub async fn post(&self, path: &str, token: &str, body: Value) -> (StatusCode, Value) {
        self.call(Method::POST, path, Some(token), Some(body)).await
    }

    /// Registers `name@example.com` and returns its token and id.
    pub async fn register(&self, name: &str) -> (String, Uuid) {
        let body = json!({ "email": email(name), "password": "test123456" });
        let (status, body) = self
            .call(Method::POST, "/auth/register", None, Some(body))
            .await;
        assert_eq!(status, StatusCode::CREATED, "{body}");
        let id = body["user"]["id"].as_str().unwrap().parse().unwrap();
        (body["token"].as_str().unwrap().to_owned(), id)
    }

    pub async fn create_memory(&self, token: &str, fields: Value) -> Value {
        let mut body = json!({
            "lat": 36.8, "lon": 10.18, "title": "Pinned",
            "media_url": "https://example.com/media.jpg",
            "media_type": "image", "visibility": "public",
            "unlock_radius_m": 200
        });
        for (key, value) in fields.as_object().unwrap() {
            body[key] = value.clone();
        }
        let (status, body) = self.post("/memories", token, body).await;
        assert_eq!(status, StatusCode::CREATED, "{body}");
        body
    }

    pub async fn befriend(&self, (a_token, a): (&str, &str), (b_token, b): (&str, &str)) {
        let (status, _) = self
            .post(
                "/friendships/request",
                a_token,
                json!({ "friend_email": email(b) }),
            )
            .await;
        assert_eq!(status, StatusCode::CREATED);
        let (status, _) = self
            .post(
                "/friendships/accept",
                b_token,
                json!({ "friend_email": email(a) }),
            )
            .await;
        assert_eq!(status, StatusCode::OK);
    }
}

pub fn email(name: &str) -> String {
    format!("{name}@example.com")
}

pub async fn json_of(response: Response<Body>) -> (StatusCode, Value) {
    let status = response.status();
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    let body = if bytes.is_empty() {
        Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap()
    };
    (status, body)
}
