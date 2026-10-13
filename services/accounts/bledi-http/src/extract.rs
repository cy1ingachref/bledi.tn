//! The axum extractors with their rejections turned into `ApiError`, so a malformed request
//! gets the same JSON error shape as every other client error.

use axum::extract::{FromRequest, FromRequestParts};
use axum::response::{IntoResponse, Response};

use crate::ApiError;

#[derive(FromRequest)]
#[from_request(via(axum::Json), rejection(ApiError))]
pub struct Json<T>(pub T);

impl<T: serde::Serialize> IntoResponse for Json<T> {
    fn into_response(self) -> Response {
        axum::Json(self.0).into_response()
    }
}

#[derive(FromRequestParts)]
#[from_request(via(axum::extract::Query), rejection(ApiError))]
pub struct Query<T>(pub T);

#[derive(FromRequestParts)]
#[from_request(via(axum::extract::Path), rejection(ApiError))]
pub struct Path<T>(pub T);
