use std::sync::Arc;

use bledi_domain::text;
use bledi_domain::user::User;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::ports::{NewUser, PasswordHasher, Result, TokenIssuer, UserStore};
use crate::{AppError, Missing, Ports};

#[derive(Debug, Deserialize)]
pub struct Register {
    pub email: String,
    pub password: String,
    pub display_name: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct Login {
    pub email: String,
    pub password: String,
}

#[derive(Debug, Serialize)]
pub struct Session {
    pub token: String,
    pub user: User,
}

#[derive(Clone)]
pub struct Accounts {
    users: Arc<dyn UserStore>,
    hasher: Arc<dyn PasswordHasher>,
    tokens: Arc<dyn TokenIssuer>,
}

impl Accounts {
    pub fn new(ports: &Ports) -> Self {
        Self {
            users: ports.users.clone(),
            hasher: ports.hasher.clone(),
            tokens: ports.tokens.clone(),
        }
    }

    pub async fn register(&self, input: Register) -> Result<Session> {
        let email = text::email(&input.email)?;
        text::password(&input.password)?;
        let display_name = text::display_name(input.display_name.as_deref())?;
        let password_hash = self.hasher.hash(&input.password).await?;
        let user = self
            .users
            .insert(NewUser {
                email,
                password_hash,
                display_name,
            })
            .await?;
        self.session(user)
    }

    pub async fn login(&self, input: Login) -> Result<Session> {
        // A malformed email takes the unknown-email path, so neither the answer nor its
        // timing says anything about which accounts exist.
        let stored = match text::email(&input.email) {
            Ok(email) => self.users.find_by_email(&email).await?,
            Err(_) => None,
        };
        let hash = stored.as_ref().map(|s| s.password_hash.as_str());
        let verified = self.hasher.verify(&input.password, hash).await?;
        match stored {
            Some(stored) if verified => self.session(stored.user),
            _ => Err(AppError::InvalidCredentials),
        }
    }

    pub async fn me(&self, user_id: Uuid) -> Result<User> {
        self.users
            .get(user_id)
            .await?
            .ok_or(AppError::NotFound(Missing::User))
    }

    pub fn authenticate(&self, token: &str) -> Result<Uuid> {
        self.tokens.verify(token)
    }

    fn session(&self, user: User) -> Result<Session> {
        Ok(Session {
            token: self.tokens.issue(&user)?,
            user,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing::Fakes;

    fn register(email: &str) -> Register {
        Register {
            email: email.into(),
            password: "test123456".into(),
            display_name: Some("  Test User ".into()),
        }
    }

    #[tokio::test]
    async fn register_normalises_the_input_and_returns_a_usable_token() {
        let accounts = Accounts::new(&Fakes::new().ports());
        let session = accounts
            .register(register(" New@Example.COM "))
            .await
            .unwrap();
        assert_eq!(session.user.email, "new@example.com");
        assert_eq!(session.user.display_name.as_deref(), Some("Test User"));
        assert_eq!(
            accounts.authenticate(&session.token).unwrap(),
            session.user.id
        );
        assert_eq!(accounts.me(session.user.id).await.unwrap(), session.user);
    }

    #[tokio::test]
    async fn register_rejects_a_taken_email_and_bad_input() {
        let accounts = Accounts::new(&Fakes::new().ports());
        accounts.register(register("a@example.com")).await.unwrap();
        let again = accounts.register(register("A@example.com")).await;
        assert!(matches!(again, Err(AppError::EmailTaken)));
        let short = Register {
            password: "short".into(),
            ..register("b@example.com")
        };
        assert_eq!(
            accounts.register(short).await.unwrap_err().code(),
            "invalid_password"
        );
    }

    #[tokio::test]
    async fn login_checks_the_password_and_hides_which_part_was_wrong() {
        let fakes = Fakes::new();
        let accounts = Accounts::new(&fakes.ports());
        accounts.register(register("a@example.com")).await.unwrap();
        let login = |email: &str, password: &str| Login {
            email: email.into(),
            password: password.into(),
        };
        assert!(accounts
            .login(login("A@example.com", "test123456"))
            .await
            .is_ok());
        for (email, password) in [
            ("a@example.com", "wrong-password"),
            ("nobody@example.com", "test123456"),
            ("not-an-email", "test123456"),
        ] {
            let err = accounts.login(login(email, password)).await.unwrap_err();
            assert!(matches!(err, AppError::InvalidCredentials), "{email}");
        }
        assert_eq!(
            fakes.hasher.unmatched_checks(),
            2,
            "unknown emails still verify"
        );
    }

    #[tokio::test]
    async fn me_reports_a_missing_user() {
        let accounts = Accounts::new(&Fakes::new().ports());
        let err = accounts.me(Uuid::new_v4()).await.unwrap_err();
        assert!(matches!(err, AppError::NotFound(Missing::User)));
    }
}
