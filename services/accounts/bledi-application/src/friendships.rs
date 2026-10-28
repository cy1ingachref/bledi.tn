use std::cmp::Reverse;
use std::collections::HashMap;
use std::sync::Arc;

use bledi_domain::friendship::{self, Friendship, FriendshipStatus, RequestAction, RequestRefused};
use bledi_domain::text;
use bledi_domain::user::User;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::ports::{FriendshipStore, Result, UserStore};
use crate::{AppError, Missing, Ports};

#[derive(Debug, Deserialize)]
pub struct FriendEmail {
    pub friend_email: String,
}

#[derive(Debug, Serialize)]
pub struct Friend {
    pub user_id: Uuid,
    pub email: String,
    pub display_name: Option<String>,
    pub status: FriendshipStatus,
}

#[derive(Debug, Serialize)]
pub struct FriendshipChange {
    pub status: FriendshipStatus,
    pub user_id: Uuid,
    pub email: String,
}

pub(crate) async fn accepted_friend_ids(
    store: &dyn FriendshipStore,
    user_id: Uuid,
) -> Result<Vec<Uuid>> {
    Ok(store
        .of(user_id)
        .await?
        .iter()
        .filter(|f| f.status == FriendshipStatus::Accepted)
        .map(|f| f.other_than(user_id))
        .collect())
}

#[derive(Clone)]
pub struct Friendships {
    users: Arc<dyn UserStore>,
    friendships: Arc<dyn FriendshipStore>,
}

impl Friendships {
    pub fn new(ports: &Ports) -> Self {
        Self {
            users: ports.users.clone(),
            friendships: ports.friendships.clone(),
        }
    }

    /// Everyone linked to `me` in either direction, by email.
    pub async fn list(&self, me: Uuid) -> Result<Vec<Friend>> {
        self.list_paginated(me, 20, 0).await
    }

    pub async fn list_paginated(
        &self,
        me: Uuid,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<Friend>> {
        let rows = self.friendships.of_paginated(me, limit, offset).await?;
        let mut friends = self.with_users(me, rows).await?;
        friends.sort_by(|a, b| a.email.cmp(&b.email));
        Ok(friends)
    }

    /// Pending requests sent to `me`, newest first.
    pub async fn requests(&self, me: Uuid) -> Result<Vec<Friend>> {
        self.requests_paginated(me, 20, 0).await
    }

    pub async fn requests_paginated(
        &self,
        me: Uuid,
        limit: usize,
        offset: usize,
    ) -> Result<Vec<Friend>> {
        let mut rows: Vec<Friendship> = self
            .friendships
            .of_paginated(me, limit, offset)
            .await?
            .into_iter()
            .filter(|f| f.friend_id == me && f.status == FriendshipStatus::Pending)
            .collect();
        rows.sort_by_key(|f| Reverse(f.created_at));
        self.with_users(me, rows).await
    }

    pub async fn request(&self, me: Uuid, input: FriendEmail) -> Result<FriendshipChange> {
        let (them, email) = self.user_by_email(&input.friend_email).await?;
        let between = if me == them {
            Vec::new()
        } else {
            self.friendships.between(me, them).await?
        };
        let status = match friendship::on_request(me, them, &between) {
            Ok(RequestAction::Send) => {
                self.friendships.request(me, them).await?;
                FriendshipStatus::Pending
            }
            Ok(RequestAction::AcceptTheirs) => {
                self.friendships.accept(them, me).await?;
                FriendshipStatus::Accepted
            }
            Err(RequestRefused::ToSelf) => return Err(AppError::SelfFriendRequest),
            Err(RequestRefused::AlreadyFriends) => return Err(AppError::AlreadyFriends),
            Err(RequestRefused::AlreadyRequested) => return Err(AppError::RequestPending),
        };
        Ok(FriendshipChange {
            status,
            user_id: them,
            email,
        })
    }

    /// Only the recipient of a pending request can accept it.
    pub async fn accept(&self, me: Uuid, input: FriendEmail) -> Result<FriendshipChange> {
        let (requester, email) = self.user_by_email(&input.friend_email).await?;
        if !self.friendships.accept(requester, me).await? {
            return Err(AppError::NotFound(Missing::FriendRequest));
        }
        Ok(FriendshipChange {
            status: FriendshipStatus::Accepted,
            user_id: requester,
            email,
        })
    }

    /// Unfriends, withdraws a request or declines one, whichever links the two.
    pub async fn remove(&self, me: Uuid, other: Uuid) -> Result<()> {
        if self.friendships.remove(me, other).await? {
            Ok(())
        } else {
            Err(AppError::NotFound(Missing::Friendship))
        }
    }

    async fn user_by_email(&self, raw: &str) -> Result<(Uuid, String)> {
        let email = text::email(raw)?;
        let stored = self
            .users
            .find_by_email(&email)
            .await?
            .ok_or(AppError::NotFound(Missing::User))?;
        Ok((stored.user.id, email))
    }

    async fn with_users(&self, me: Uuid, rows: Vec<Friendship>) -> Result<Vec<Friend>> {
        let ids: Vec<Uuid> = rows.iter().map(|f| f.other_than(me)).collect();
        let users: HashMap<Uuid, User> = self
            .users
            .get_many(&ids)
            .await?
            .into_iter()
            .map(|u| (u.id, u))
            .collect();
        Ok(rows
            .iter()
            .filter_map(|f| {
                let user = users.get(&f.other_than(me))?;
                Some(Friend {
                    user_id: user.id,
                    email: user.email.clone(),
                    display_name: user.display_name.clone(),
                    status: f.status,
                })
            })
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::testing::Fakes;

    fn ask(email: &str) -> FriendEmail {
        FriendEmail {
            friend_email: email.into(),
        }
    }

    #[tokio::test]
    async fn a_request_then_an_acceptance_makes_two_friends() {
        let fakes = Fakes::new();
        let friendships = Friendships::new(&fakes.ports());
        let alice = fakes.user("alice@example.com").await;
        let bob = fakes.user("bob@example.com").await;

        let sent = friendships
            .request(alice, ask("BOB@example.com"))
            .await
            .unwrap();
        assert_eq!(sent.status, FriendshipStatus::Pending);
        assert_eq!(sent.user_id, bob);
        let incoming = friendships.requests(bob).await.unwrap();
        assert_eq!(incoming.len(), 1);
        assert_eq!(incoming[0].email, "alice@example.com");
        assert!(friendships.requests(alice).await.unwrap().is_empty());

        let err = friendships
            .request(alice, ask("bob@example.com"))
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::RequestPending));
        let err = friendships
            .accept(alice, ask("bob@example.com"))
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::NotFound(Missing::FriendRequest)));

        friendships
            .accept(bob, ask("alice@example.com"))
            .await
            .unwrap();
        for (me, other) in [(alice, "bob@example.com"), (bob, "alice@example.com")] {
            let list = friendships.list(me).await.unwrap();
            assert_eq!(list.len(), 1);
            assert_eq!(list[0].email, other);
            assert_eq!(list[0].status, FriendshipStatus::Accepted);
        }
        let err = friendships
            .request(bob, ask("alice@example.com"))
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::AlreadyFriends));
    }

    #[tokio::test]
    async fn asking_back_accepts_the_pending_request() {
        let fakes = Fakes::new();
        let friendships = Friendships::new(&fakes.ports());
        let alice = fakes.user("alice@example.com").await;
        let bob = fakes.user("bob@example.com").await;

        friendships
            .request(alice, ask("bob@example.com"))
            .await
            .unwrap();
        let back = friendships
            .request(bob, ask("alice@example.com"))
            .await
            .unwrap();
        assert_eq!(back.status, FriendshipStatus::Accepted);
        assert_eq!(
            friendships.list(alice).await.unwrap()[0].status,
            FriendshipStatus::Accepted
        );
    }

    #[tokio::test]
    async fn yourself_and_unknown_users_are_refused() {
        let fakes = Fakes::new();
        let friendships = Friendships::new(&fakes.ports());
        let alice = fakes.user("alice@example.com").await;
        let err = friendships
            .request(alice, ask("alice@example.com"))
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::SelfFriendRequest));
        let err = friendships
            .request(alice, ask("nobody@example.com"))
            .await
            .unwrap_err();
        assert!(matches!(err, AppError::NotFound(Missing::User)));
    }

    #[tokio::test]
    async fn removing_unlinks_both_sides_once() {
        let fakes = Fakes::new();
        let friendships = Friendships::new(&fakes.ports());
        let alice = fakes.user("alice@example.com").await;
        let bob = fakes.user("bob@example.com").await;
        friendships
            .request(alice, ask("bob@example.com"))
            .await
            .unwrap();
        friendships.remove(bob, alice).await.unwrap();
        assert!(friendships.list(alice).await.unwrap().is_empty());
        let err = friendships.remove(alice, bob).await.unwrap_err();
        assert!(matches!(err, AppError::NotFound(Missing::Friendship)));
    }
}
