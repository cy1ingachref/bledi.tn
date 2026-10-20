//! First-party media: an uploaded photo is written under the media root and served back
//! from `/api/v1/media/{key}`.
//!
//! The key is the source of truth and the URL is derived from it, so a change of host or
//! path rewrites the URL without touching a stored row.

use std::path::{Path, PathBuf};

use axum::body::Body;
use axum::extract::State;
use axum::http::{header, HeaderValue, StatusCode};
use axum::response::Response;
use uuid::Uuid;

use bledi_application::AppError;

use crate::auth::AuthUser;
use crate::exif;
use crate::extract::Path as PathParam;
use crate::{ApiError, AppState};

/// The largest photo the server accepts.
pub const MAX_UPLOAD_BYTES: usize = 10 * 1024 * 1024;

/// Where the photos live, and the only way to read them back.
#[derive(Clone)]
pub struct MediaStore {
    root: PathBuf,
}

impl MediaStore {
    pub fn new(root: impl Into<PathBuf>) -> std::io::Result<Self> {
        let root = root.into();
        std::fs::create_dir_all(&root)?;
        Ok(Self { root })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// The key is a plain file name by the time it reaches here, so it cannot name a
    /// directory or climb out of the root.
    fn path_for(&self, key: &str) -> PathBuf {
        self.root.join(key)
    }

    /// A key that could climb out of the root is refused here, at the last point before the
    /// filesystem, and not only where the application validates it.
    fn plain_file_name(key: &str) -> bool {
        !key.is_empty()
            && key != "."
            && key != ".."
            && !key.contains('/')
            && !key.contains('\\')
            && !key.contains('\0')
    }

    pub async fn save(&self, key: &str, bytes: &[u8]) -> Result<(), ApiError> {
        if !Self::plain_file_name(key) {
            return Err(bad_key());
        }
        tokio::fs::write(self.path_for(key), bytes)
            .await
            .map_err(|e| ApiError::from(AppError::internal(format!("write media {key}: {e}"))))
    }

    pub async fn remove(&self, key: &str) {
        if !Self::plain_file_name(key) {
            return;
        }
        let _ = tokio::fs::remove_file(self.path_for(key)).await;
    }

    pub async fn read(&self, key: &str) -> Result<Vec<u8>, ApiError> {
        if !Self::plain_file_name(key) {
            return Err(bad_key());
        }
        tokio::fs::read(self.path_for(key))
            .await
            .map_err(|e| match e.kind() {
                std::io::ErrorKind::NotFound => {
                    ApiError::from(AppError::NotFound(bledi_application::Missing::Memory))
                }
                _ => ApiError::from(AppError::internal(format!("read media {key}: {e}"))),
            })
    }
}

fn bad_key() -> ApiError {
    ApiError::BadRequest {
        status: StatusCode::BAD_REQUEST,
        message: "the media key is not a file name".into(),
    }
}

/// A photo that has been checked and cleaned, ready to be stored.
#[derive(Debug)]
pub struct Prepared {
    pub key: String,
    pub bytes: Vec<u8>,
}

/// Checks the bytes against the container they claim to be, drops the metadata and names
/// the file.
///
/// The type comes from the magic number, never from the client's `Content-Type`: a `.jpg`
/// that is really an HTML file must not be stored as a photo.
pub fn prepare(bytes: &[u8]) -> Result<Prepared, ApiError> {
    if bytes.len() > MAX_UPLOAD_BYTES {
        return Err(ApiError::BadRequest {
            status: StatusCode::PAYLOAD_TOO_LARGE,
            message: format!("the photo must be at most {MAX_UPLOAD_BYTES} bytes"),
        });
    }
    let extension = if exif::is_jpeg(bytes) {
        "jpg"
    } else if exif::is_png(bytes) {
        "png"
    } else {
        return Err(ApiError::BadRequest {
            status: StatusCode::BAD_REQUEST,
            message: "the photo must be a JPEG or a PNG".into(),
        });
    };
    Ok(Prepared {
        key: format!("{}.{extension}", Uuid::new_v4()),
        bytes: exif::strip_exif(bytes),
    })
}

/// Serves an uploaded photo to the people who are allowed to see the memory it belongs to.
pub async fn serve(
    State(state): State<AppState>,
    AuthUser(me): AuthUser,
    PathParam(key): PathParam<String>,
) -> Result<Response, ApiError> {
    // The memory decides who may see the photo; the file is never served on its own.
    state.services.memories.media_for(me, &key).await?;
    let bytes = state.media.read(&key).await?;
    let mime = if exif::is_jpeg(&bytes) {
        "image/jpeg"
    } else if exif::is_png(&bytes) {
        "image/png"
    } else {
        "application/octet-stream"
    };
    let mut response = Response::new(Body::from(bytes));
    response
        .headers_mut()
        .insert(header::CONTENT_TYPE, HeaderValue::from_static(mime));
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("private, max-age=300"),
    );
    response.headers_mut().insert(
        "x-content-type-options",
        HeaderValue::from_static("nosniff"),
    );
    Ok(response)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_type_comes_from_the_bytes_not_the_name() {
        let jpeg = [0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x04, 0x00, 0x00];
        let prepared = prepare(&jpeg).unwrap();
        assert!(prepared.key.ends_with(".jpg"));
        let png = [0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A, 0x00];
        assert!(prepare(&png).unwrap().key.ends_with(".png"));
    }

    #[test]
    fn a_file_that_is_not_an_image_is_refused() {
        let html = b"<!doctype html><html></html>";
        match prepare(html).unwrap_err() {
            ApiError::BadRequest { status, message } => {
                assert_eq!(status, StatusCode::BAD_REQUEST);
                assert!(message.contains("JPEG"), "{message}");
            }
            other => panic!("expected a bad request, got {other:?}"),
        }
    }

    #[test]
    fn two_uploads_get_two_different_keys() {
        let jpeg = [0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x04, 0x00, 0x00];
        assert_ne!(prepare(&jpeg).unwrap().key, prepare(&jpeg).unwrap().key);
    }
}
