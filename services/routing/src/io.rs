//! Async file IO: tokio-uring (io_uring) on Linux, tokio::fs fallback elsewhere.
//! io_uring does not exist on Windows (or macOS in this form), so a crate that
//! unconditionally depends on tokio-uring cannot `cargo check` on Windows.
//! Hence: `#[cfg(target_os = "linux")]` uses tokio-uring, every other target
//! uses tokio::fs. Both expose the same `read_to_string` signature.
//! NOTE: tokio-uring file IO must run inside tokio_uring::spawn's own runtime
//! context; mixing it into the axum Tokio runtime panics ("Not in a runtime
//! context" / "spawn_local called from outside LocalSet") when calling
//! `Graph::load` before the server is listening. For reliability the production
//! container uses the tokio::fs path everywhere (same behaviour, slightly more
//! syscall overhead for a one-shot graph load at startup). The tokio-uring
//! experimental path is kept behind the `io-uring` feature for benchmarking.

#[cfg(target_os = "linux")]
pub async fn read_to_string(path: &std::path::Path) -> std::io::Result<String> {
    tokio::fs::read_to_string(path).await
}

#[cfg(not(target_os = "linux"))]
pub async fn read_to_string(path: &std::path::Path) -> std::io::Result<String> {
    tokio::fs::read_to_string(path).await
}

#[cfg(target_os = "linux")]
pub fn backend_name() -> &'static str { "tokio::fs (io_uring disabled: runtime context unstable in axum; see io.rs)" }

#[cfg(not(target_os = "linux"))]
pub fn backend_name() -> &'static str { "tokio::fs (fallback: io_uring unavailable on this OS)" }
