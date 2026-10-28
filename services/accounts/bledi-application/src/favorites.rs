use std::sync::Arc;

use bledi_domain::favorite::{Favorite, FavoriteKind};
use bledi_domain::text;
use serde::Deserialize;
use uuid::Uuid;

use crate::ports::{FavoriteStore, NewFavorite, Result};
use crate::{AppError, Missing, Ports};

#[derive(Debug, Deserialize)]
pub struct SaveFavorite {
    pub kind: FavoriteKind,
    pub ref_id: String,
    pub label: Option<String>,
}

#[derive(Clone)]
pub struct Favorites {
    favorites: Arc<dyn FavoriteStore>,
}

impl Favorites {
    pub fn new(ports: &Ports) -> Self {
        Self {
            favorites: ports.favorites.clone(),
        }
    }

    pub async fn list(&self, me: Uuid) -> Result<Vec<Favorite>> {
        self.list_paginated(me, 20, 0).await
    }

    pub async fn list_paginated(
        &self,
        me: Uuid,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<Favorite>> {
        self.favorites.owned_by_paginated(me, limit, offset).await
    }

    pub async fn save(&self, me: Uuid, input: SaveFavorite) -> Result<Favorite> {
        let favorite = NewFavorite {
            user_id: me,
            ref_id: text::ref_id(&input.ref_id)?,
            label: text::label(input.label.as_deref())?,
            kind: input.kind,
        };
        self.favorites.upsert(favorite).await
    }

    pub async fn delete(&self, me: Uuid, id: Uuid) -> Result<()> {
        if self.favorites.delete(id, me).await? {
            Ok(())
        } else {
            Err(AppError::NotFound(Missing::Favorite))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing::Fakes;

    fn station(label: &str) -> SaveFavorite {
        SaveFavorite {
            kind: FavoriteKind::Station,
            ref_id: " test_station ".into(),
            label: Some(label.into()),
        }
    }

    #[tokio::test]
    async fn saving_the_same_place_again_replaces_its_label() {
        let fakes = Fakes::new();
        let favorites = Favorites::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let first = favorites.save(me, station("Home")).await.unwrap();
        assert_eq!(first.ref_id, "test_station");
        let second = favorites.save(me, station("Work")).await.unwrap();
        assert_eq!(second.id, first.id);
        let list = favorites.list(me).await.unwrap();
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].label.as_deref(), Some("Work"));
    }

    #[tokio::test]
    async fn only_the_owner_deletes() {
        let fakes = Fakes::new();
        let favorites = Favorites::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let other = fakes.user("other@example.com").await;
        let saved = favorites.save(me, station("Home")).await.unwrap();
        let err = favorites.delete(other, saved.id).await.unwrap_err();
        assert!(matches!(err, AppError::NotFound(Missing::Favorite)));
        favorites.delete(me, saved.id).await.unwrap();
        assert!(favorites.list(me).await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn an_empty_ref_id_is_rejected() {
        let fakes = Fakes::new();
        let favorites = Favorites::new(&fakes.ports());
        let me = fakes.user("me@example.com").await;
        let blank = SaveFavorite {
            ref_id: "  ".into(),
            ..station("x")
        };
        assert_eq!(
            favorites.save(me, blank).await.unwrap_err().code(),
            "invalid_text"
        );
    }
}
