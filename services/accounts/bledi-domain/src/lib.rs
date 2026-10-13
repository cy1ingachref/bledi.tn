mod error;
pub mod favorite;
pub mod friendship;
pub mod geo;
pub mod location_share;
pub mod memory;
pub mod text;
pub mod user;

pub use error::{Invalid, UnknownVariant, ValidationError};

/// A closed set of lowercase names, stored as text or a Postgres enum and sent as JSON strings.
macro_rules! string_enum {
    ($name:ident { $($variant:ident => $text:literal),+ $(,)? }) => {
        #[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
        #[serde(rename_all = "lowercase")]
        pub enum $name {
            $($variant),+
        }

        impl $name {
            pub fn as_str(self) -> &'static str {
                match self {
                    $(Self::$variant => $text),+
                }
            }
        }

        impl TryFrom<String> for $name {
            type Error = $crate::UnknownVariant;

            fn try_from(value: String) -> Result<Self, Self::Error> {
                match value.as_str() {
                    $($text => Ok(Self::$variant),)+
                    _ => Err($crate::UnknownVariant(value)),
                }
            }
        }
    };
}
pub(crate) use string_enum;
