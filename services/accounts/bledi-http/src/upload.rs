//! A create-memory request, either JSON or a multipart form carrying a photo.

use std::collections::HashMap;

use axum::async_trait;
use axum::body::{Body, Bytes};
use axum::extract::{FromRequest, Multipart};
use axum::http::{header, Request, StatusCode};
use axum::Json;
use bledi_application::memories::CreateMemory;
use serde_json::{json, Map, Value};

use crate::ApiError;

/// The fields of a create-memory request, plus the photo when one was uploaded.
pub struct CreateMemoryBody {
    pub memory: CreateMemory,
    pub photo: Option<Bytes>,
}

fn bad(message: impl Into<String>) -> ApiError {
    ApiError::BadRequest {
        status: StatusCode::BAD_REQUEST,
        message: message.into(),
    }
}

#[async_trait]
impl<S> FromRequest<S> for CreateMemoryBody
where
    S: Send + Sync,
{
    type Rejection = ApiError;

    async fn from_request(req: Request<Body>, state: &S) -> Result<Self, Self::Rejection> {
        let content_type = req
            .headers()
            .get(header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
            .to_ascii_lowercase();

        if content_type.starts_with("multipart/form-data") {
            Self::from_multipart(req, state).await
        } else {
            let Json(memory) = Json::<CreateMemory>::from_request(req, state)
                .await
                .map_err(|e| ApiError::BadRequest {
                    status: e.status(),
                    message: e.body_text(),
                })?;
            Ok(Self {
                memory,
                photo: None,
            })
        }
    }
}

impl CreateMemoryBody {
    async fn from_multipart<S: Send + Sync>(
        req: Request<Body>,
        state: &S,
    ) -> Result<Self, ApiError> {
        let mut multipart =
            Multipart::from_request(req, state)
                .await
                .map_err(|e| ApiError::BadRequest {
                    status: e.status(),
                    message: e.body_text(),
                })?;

        let mut fields: HashMap<String, String> = HashMap::new();
        let mut photo = None;
        while let Some(field) = multipart
            .next_field()
            .await
            .map_err(|e| bad(e.body_text()))?
        {
            let name = field.name().unwrap_or_default().to_owned();
            if name == "photo" {
                photo = Some(field.bytes().await.map_err(|e| bad(e.body_text()))?);
            } else {
                let text = field.text().await.map_err(|e| bad(e.body_text()))?;
                fields.insert(name, text);
            }
        }
        Ok(Self {
            memory: memory_from_fields(&fields)?,
            photo,
        })
    }
}

/// Turns the text fields of a form into a memory.
///
/// `media_url` and `media_key` are ignored: the photo's key comes from the upload, so a
/// form cannot point a memory at a host the client controls.
fn memory_from_fields(fields: &HashMap<String, String>) -> Result<CreateMemory, ApiError> {
    let mut value = Map::new();
    for (key, raw) in fields {
        match key.as_str() {
            "title" | "description" | "visibility" | "media_type" => {
                value.insert(key.clone(), json!(raw));
            }
            "lat" | "lon" | "unlock_radius_m" => {
                let number: f64 = raw
                    .trim()
                    .parse()
                    .map_err(|_| bad(format!("{key} must be a number")))?;
                value.insert(key.clone(), json!(number));
            }
            _ => {}
        }
    }
    // A form that carries a photo does not have to name its type: a photo is an image.
    value.entry("media_type").or_insert_with(|| json!("image"));
    serde_json::from_value(Value::Object(value))
        .map_err(|e| bad(format!("invalid memory fields: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fields(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    #[test]
    fn a_form_becomes_a_memory() {
        let memory = memory_from_fields(&fields(&[
            ("lat", "36.8"),
            ("lon", "10.18"),
            ("title", "Pinned"),
            ("media_type", "image"),
            ("visibility", "public"),
            ("unlock_radius_m", "200"),
        ]))
        .unwrap();
        assert_eq!(memory.lat, 36.8);
        assert_eq!(memory.title.as_deref(), Some("Pinned"));
        assert_eq!(memory.unlock_radius_m, 200.0);
    }

    #[test]
    fn a_form_cannot_point_at_another_host() {
        let memory = memory_from_fields(&fields(&[
            ("lat", "36.8"),
            ("lon", "10.18"),
            ("media_url", "https://evil.example/tracker.gif"),
            ("media_key", "someone-elses-key.jpg"),
            ("media_type", "image"),
            ("visibility", "public"),
            ("unlock_radius_m", "200"),
        ]))
        .unwrap();
        assert!(memory.media_url.is_none());
        assert!(memory.media_key.is_none());
    }

    #[test]
    fn a_form_without_the_required_fields_is_refused() {
        let err = memory_from_fields(&fields(&[("lat", "36.8")])).unwrap_err();
        match err {
            ApiError::BadRequest { status, message } => {
                assert_eq!(status, StatusCode::BAD_REQUEST);
                assert!(message.contains("invalid memory fields"), "{message}");
            }
            other => panic!("expected a bad request, got {other:?}"),
        }
    }

    #[test]
    fn a_non_numeric_coordinate_is_refused() {
        let err = memory_from_fields(&fields(&[("lat", "north")])).unwrap_err();
        match err {
            ApiError::BadRequest { message, .. } => assert!(message.contains("lat"), "{message}"),
            other => panic!("expected a bad request, got {other:?}"),
        }
    }
}
