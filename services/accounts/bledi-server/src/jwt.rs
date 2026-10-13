use bledi_application::ports::{Result, TokenIssuer};
use bledi_application::AppError;
use bledi_domain::user::User;
use chrono::{Duration, Utc};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

const TOKEN_LIFETIME: Duration = Duration::days(7);

#[derive(Serialize, Deserialize)]
struct Claims {
    sub: Uuid,
    email: String,
    exp: i64,
    iat: i64,
}

/// HS256 tokens. The secret is checked for length by the config before it gets here.
pub struct JwtTokenIssuer {
    encoding: EncodingKey,
    decoding: DecodingKey,
}

impl JwtTokenIssuer {
    pub fn new(secret: &[u8]) -> Self {
        Self {
            encoding: EncodingKey::from_secret(secret),
            decoding: DecodingKey::from_secret(secret),
        }
    }
}

impl TokenIssuer for JwtTokenIssuer {
    fn issue(&self, user: &User) -> Result<String> {
        let now = Utc::now();
        let claims = Claims {
            sub: user.id,
            email: user.email.clone(),
            exp: (now + TOKEN_LIFETIME).timestamp(),
            iat: now.timestamp(),
        };
        encode(&Header::default(), &claims, &self.encoding).map_err(AppError::internal)
    }

    fn verify(&self, token: &str) -> Result<Uuid> {
        decode::<Claims>(token, &self.decoding, &Validation::default())
            .map(|data| data.claims.sub)
            .map_err(|_| AppError::Unauthorized("Invalid or expired token"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn user() -> User {
        User {
            id: Uuid::new_v4(),
            email: "roundtrip@example.com".into(),
            display_name: None,
            created_at: Utc::now(),
        }
    }

    #[test]
    fn a_token_verifies_to_its_user() {
        let issuer = JwtTokenIssuer::new(b"a-test-secret-that-is-long-enough!!");
        let user = user();
        let token = issuer.issue(&user).unwrap();
        assert_eq!(issuer.verify(&token).unwrap(), user.id);
    }

    #[test]
    fn a_token_from_another_secret_or_garbage_is_refused() {
        let token = JwtTokenIssuer::new(b"secret-number-one-long-enough-here")
            .issue(&user())
            .unwrap();
        let other = JwtTokenIssuer::new(b"secret-number-two-long-enough-here");
        for token in [token.as_str(), "not.a.token", ""] {
            assert!(matches!(
                other.verify(token),
                Err(AppError::Unauthorized(_))
            ));
        }
    }

    #[test]
    fn an_expired_token_is_refused() {
        let secret = b"a-test-secret-that-is-long-enough!!";
        let past = (Utc::now() - Duration::days(1)).timestamp();
        let claims = Claims {
            sub: Uuid::new_v4(),
            email: "old@example.com".into(),
            exp: past,
            iat: past - 60,
        };
        let token = encode(
            &Header::default(),
            &claims,
            &EncodingKey::from_secret(secret),
        )
        .unwrap();
        assert!(JwtTokenIssuer::new(secret).verify(&token).is_err());
    }
}
