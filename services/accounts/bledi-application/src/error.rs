use std::fmt;

use bledi_domain::ValidationError;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Missing {
    User,
    Memory,
    Favorite,
    LocationShare,
    Friendship,
    FriendRequest,
}

/// Every failure a use case can report. `code` is the closed set of public error codes.
#[derive(Debug)]
pub enum AppError {
    Invalid(ValidationError),
    InvalidCredentials,
    Unauthorized(&'static str),
    EmailTaken,
    NotFound(Missing),
    Forbidden,
    TooFar {
        distance_m: f64,
        unlock_radius_m: f64,
    },
    SelfFriendRequest,
    AlreadyFriends,
    RequestPending,
    /// The detail is for the log only, never for the client.
    Internal(String),
}

impl AppError {
    pub fn internal(detail: impl fmt::Display) -> Self {
        Self::Internal(detail.to_string())
    }

    pub fn code(&self) -> &'static str {
        match self {
            Self::Invalid(e) => e.kind.code(),
            Self::InvalidCredentials => "invalid_credentials",
            Self::Unauthorized(_) => "unauthorized",
            Self::EmailTaken => "email_taken",
            Self::NotFound(_) => "not_found",
            Self::Forbidden => "forbidden",
            Self::TooFar { .. } => "too_far",
            Self::SelfFriendRequest => "self_friend_request",
            Self::AlreadyFriends => "already_friends",
            Self::RequestPending => "request_pending",
            Self::Internal(_) => "internal",
        }
    }
}

impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Invalid(e) => &e.message,
            Self::InvalidCredentials => "Invalid credentials",
            Self::Unauthorized(reason) => reason,
            Self::EmailTaken => "Email already registered",
            Self::NotFound(Missing::User) => "User not found",
            Self::NotFound(Missing::Memory) => "Memory not found",
            Self::NotFound(Missing::Favorite) => "Favorite not found",
            Self::NotFound(Missing::LocationShare) => "Location share not found",
            Self::NotFound(Missing::Friendship) => "Friendship not found",
            Self::NotFound(Missing::FriendRequest) => "No pending request",
            Self::Forbidden => "Access denied",
            Self::TooFar { .. } => "Too far from this memory",
            Self::SelfFriendRequest => "You cannot send a friend request to yourself",
            Self::AlreadyFriends => "Already friends",
            Self::RequestPending => "Friend request already pending",
            Self::Internal(_) => "internal",
        })
    }
}

impl std::error::Error for AppError {}

impl From<ValidationError> for AppError {
    fn from(e: ValidationError) -> Self {
        Self::Invalid(e)
    }
}
