use axum::extract::rejection::{JsonRejection, PathRejection, QueryRejection};
use axum::http::{header, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use bledi_application::AppError;
use serde_json::{json, Value};

/// Every error a handler returns. Client errors carry the human message in `error`, which the
/// apps display as is, and a stable `code`. Server errors say only `internal`.
#[derive(Debug)]
pub enum ApiError {
    App(AppError),
    RateLimited { retry_after_secs: u64 },
    BadRequest { status: StatusCode, message: String },
}

impl From<AppError> for ApiError {
    fn from(e: AppError) -> Self {
        Self::App(e)
    }
}

macro_rules! from_rejection {
    ($($rejection:ty),*) => {$(
        impl From<$rejection> for ApiError {
            fn from(r: $rejection) -> Self {
                Self::BadRequest { status: r.status(), message: r.body_text() }
            }
        }
    )*};
}
from_rejection!(JsonRejection, QueryRejection, PathRejection);

fn status(e: &AppError) -> StatusCode {
    match e {
        AppError::Invalid(_) | AppError::SelfFriendRequest => StatusCode::BAD_REQUEST,
        AppError::InvalidCredentials | AppError::Unauthorized(_) => StatusCode::UNAUTHORIZED,
        AppError::Forbidden | AppError::TooFar { .. } => StatusCode::FORBIDDEN,
        AppError::NotFound(_) => StatusCode::NOT_FOUND,
        AppError::EmailTaken | AppError::AlreadyFriends | AppError::RequestPending => {
            StatusCode::CONFLICT
        }
        AppError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

fn body(e: &AppError) -> Value {
    let mut body = json!({ "error": e.to_string(), "code": e.code() });
    if let AppError::TooFar {
        distance_m,
        unlock_radius_m,
    } = e
    {
        body["distance_m"] = json!(distance_m.round());
        body["unlock_radius_m"] = json!(unlock_radius_m);
    }
    body
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        match self {
            Self::App(AppError::Internal(detail)) => {
                tracing::error!("{detail}");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({ "error": "internal" })),
                )
                    .into_response()
            }
            Self::App(e) => (status(&e), Json(body(&e))).into_response(),
            Self::RateLimited { retry_after_secs } => {
                let body = json!({
                    "error": "Too many requests",
                    "code": "rate_limited",
                    "retry_after_secs": retry_after_secs,
                });
                let mut response = (StatusCode::TOO_MANY_REQUESTS, Json(body)).into_response();
                response
                    .headers_mut()
                    .insert(header::RETRY_AFTER, HeaderValue::from(retry_after_secs));
                response
            }
            Self::BadRequest { status, message } => (
                status,
                Json(json!({ "error": message, "code": "invalid_request" })),
            )
                .into_response(),
        }
    }
}
