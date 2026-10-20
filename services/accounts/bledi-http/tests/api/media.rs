use axum::body::Body;
use axum::http::{header, Request, StatusCode};
use http_body_util::BodyExt;

use crate::support::{json_of, TestApp};

const BOUNDARY: &str = "----bledi-test-boundary";

/// A JPEG with an APP1/EXIF segment, the way a phone photo carries its GPS tag.
fn jpeg() -> Vec<u8> {
    let mut bytes = vec![0xFF, 0xD8];
    let payload = b"Exif\0\0GPS-LATITUDE-36.8";
    let len = (payload.len() + 2) as u16;
    bytes.extend_from_slice(&[0xFF, 0xE1]);
    bytes.extend_from_slice(&len.to_be_bytes());
    bytes.extend_from_slice(payload);
    bytes.extend_from_slice(&[0xFF, 0xE0, 0x00, 0x04, 0x00, 0x00]);
    bytes.extend_from_slice(&[0xFF, 0xDA, 0x00, 0x02]);
    bytes.extend_from_slice(&[0xAA, 0xBB, 0xCC]);
    bytes.extend_from_slice(&[0xFF, 0xD9]);
    bytes
}

/// A form carrying the memory fields and, optionally, a photo.
fn form(fields: &[(&str, &str)], photo: Option<&[u8]>, token: &str) -> Request<Body> {
    let mut body = Vec::new();
    for (name, value) in fields {
        body.extend_from_slice(
            format!(
                "--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
            )
            .as_bytes(),
        );
    }
    if let Some(bytes) = photo {
        body.extend_from_slice(
            format!(
                "--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"photo\"; \
                 filename=\"photo.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n"
            )
            .as_bytes(),
        );
        body.extend_from_slice(bytes);
        body.extend_from_slice(b"\r\n");
    }
    body.extend_from_slice(format!("--{BOUNDARY}--\r\n").as_bytes());

    Request::post("/api/v1/memories")
        .header(
            header::CONTENT_TYPE,
            format!("multipart/form-data; boundary={BOUNDARY}"),
        )
        .header(header::AUTHORIZATION, format!("Bearer {token}"))
        .body(Body::from(body))
        .unwrap()
}

const FIELDS: &[(&str, &str)] = &[
    ("lat", "36.8"),
    ("lon", "10.18"),
    ("title", "Pinned"),
    ("visibility", "public"),
    ("unlock_radius_m", "200"),
];

#[tokio::test]
async fn an_uploaded_photo_is_stored_stripped_and_served() {
    let app = TestApp::new();
    let (token, _) = app.register("uploader").await;

    let (status, created) = json_of(app.send(form(FIELDS, Some(&jpeg()), &token)).await).await;
    assert_eq!(status, StatusCode::CREATED, "{created}");

    let media_url = created["media_url"].as_str().unwrap().to_owned();
    assert!(media_url.starts_with("/api/v1/media/"), "{media_url}");
    let key = media_url.rsplit('/').next().unwrap().to_owned();

    let request = Request::get(format!("/api/v1/media/{key}"))
        .header(header::AUTHORIZATION, format!("Bearer {token}"))
        .body(Body::empty())
        .unwrap();
    let response = app.send(request).await;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(response.headers()[header::CONTENT_TYPE], "image/jpeg");

    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    assert!(
        !bytes.windows(5).any(|w| w == b"Exif\0"),
        "the EXIF block must be gone"
    );
    assert!(
        !bytes.windows(4).any(|w| w == b"GPS-"),
        "the GPS tag must be gone"
    );
}

#[tokio::test]
async fn a_file_that_is_not_a_photo_is_refused() {
    let app = TestApp::new();
    let (token, _) = app.register("liar").await;
    let html = b"<!doctype html><html><script>alert(1)</script></html>";

    let (status, body) = json_of(app.send(form(FIELDS, Some(html), &token)).await).await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "{body}");
    assert_eq!(body["code"], "invalid_request");
}

#[tokio::test]
async fn a_key_that_climbs_out_of_the_media_root_is_refused() {
    let app = TestApp::new();
    let (token, _) = app.register("crawler").await;

    for key in ["..%2F..%2Fetc%2Fpasswd", "..", "%2Fetc%2Fpasswd"] {
        let request = Request::get(format!("/api/v1/media/{key}"))
            .header(header::AUTHORIZATION, format!("Bearer {token}"))
            .body(Body::empty())
            .unwrap();
        let (status, body) = json_of(app.send(request).await).await;
        assert!(
            status.is_client_error(),
            "{key} must not reach the filesystem: {status}"
        );
        assert_eq!(body["code"], "invalid_media_key", "{body}");
    }
}

#[tokio::test]
async fn a_private_photo_is_not_served_to_another_user() {
    let app = TestApp::new();
    let (owner, _) = app.register("owner").await;
    let (stranger, _) = app.register("stranger").await;

    let fields: &[(&str, &str)] = &[
        ("lat", "36.8"),
        ("lon", "10.18"),
        ("visibility", "private"),
        ("unlock_radius_m", "200"),
    ];
    let (status, created) = json_of(app.send(form(fields, Some(&jpeg()), &owner)).await).await;
    assert_eq!(status, StatusCode::CREATED, "{created}");
    let key = created["media_url"]
        .as_str()
        .unwrap()
        .rsplit('/')
        .next()
        .unwrap()
        .to_owned();

    let request = Request::get(format!("/api/v1/media/{key}"))
        .header(header::AUTHORIZATION, format!("Bearer {stranger}"))
        .body(Body::empty())
        .unwrap();
    let (status, body) = json_of(app.send(request).await).await;
    assert_eq!(status, StatusCode::FORBIDDEN, "{body}");
    assert_eq!(body["code"], "forbidden");
}
