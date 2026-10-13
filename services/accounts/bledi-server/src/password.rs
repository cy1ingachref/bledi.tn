use std::sync::OnceLock;

use async_trait::async_trait;
use bledi_application::ports::{PasswordHasher, Result};
use bledi_application::AppError;

/// bcrypt on the blocking pool: one check costs tens of milliseconds of CPU, which would
/// otherwise stall every request sharing the runtime thread.
pub struct BcryptPasswordHasher;

/// Checked when the email is unknown, so that path costs as much as a wrong password.
fn dummy_hash() -> &'static str {
    static DUMMY: OnceLock<String> = OnceLock::new();
    DUMMY.get_or_init(|| {
        bcrypt::hash("timing-equalisation-placeholder", bcrypt::DEFAULT_COST)
            .expect("bcrypt can hash a constant")
    })
}

async fn blocking<T: Send + 'static>(f: impl FnOnce() -> T + Send + 'static) -> Result<T> {
    tokio::task::spawn_blocking(f)
        .await
        .map_err(AppError::internal)
}

#[async_trait]
impl PasswordHasher for BcryptPasswordHasher {
    async fn hash(&self, password: &str) -> Result<String> {
        let password = password.to_owned();
        blocking(move || bcrypt::hash(password, bcrypt::DEFAULT_COST))
            .await?
            .map_err(AppError::internal)
    }

    async fn verify(&self, password: &str, hash: Option<&str>) -> Result<bool> {
        let password = password.to_owned();
        let (hash, known) = match hash {
            Some(hash) => (hash.to_owned(), true),
            None => (dummy_hash().to_owned(), false),
        };
        let matches = blocking(move || bcrypt::verify(password, &hash).unwrap_or(false)).await?;
        Ok(known && matches)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn verifies_its_own_hashes_only() {
        let hasher = BcryptPasswordHasher;
        let hash = hasher.hash("test123456").await.unwrap();
        assert!(hasher.verify("test123456", Some(&hash)).await.unwrap());
        assert!(!hasher.verify("wrong", Some(&hash)).await.unwrap());
        assert!(!hasher
            .verify("test123456", Some("not-a-hash"))
            .await
            .unwrap());
        assert!(!hasher
            .verify("timing-equalisation-placeholder", None)
            .await
            .unwrap());
    }
}
