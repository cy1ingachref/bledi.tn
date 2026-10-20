use std::fmt;

/// What kind of input was rejected. Each kind is one public error code.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Invalid {
    Coordinates,
    Radius,
    Accuracy,
    Email,
    Password,
    Text,
    MediaUrl,
    MediaKey,
    Expiry,
}

impl Invalid {
    pub fn code(self) -> &'static str {
        match self {
            Self::Coordinates => "invalid_coordinates",
            Self::Radius => "invalid_radius",
            Self::Accuracy => "invalid_accuracy",
            Self::Email => "invalid_email",
            Self::Password => "invalid_password",
            Self::Text => "invalid_text",
            Self::MediaUrl => "invalid_media_url",
            Self::MediaKey => "invalid_media_key",
            Self::Expiry => "invalid_expiry",
        }
    }
}

/// Rejected input. The message names the field so the client can tell the user which one is wrong.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValidationError {
    pub kind: Invalid,
    pub message: String,
}

impl ValidationError {
    pub fn new(kind: Invalid, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }
}

impl fmt::Display for ValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for ValidationError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnknownVariant(pub String);

impl fmt::Display for UnknownVariant {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "unknown variant {:?}", self.0)
    }
}

impl std::error::Error for UnknownVariant {}
