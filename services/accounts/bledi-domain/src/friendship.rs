use chrono::{DateTime, Utc};
use uuid::Uuid;

use crate::string_enum;

string_enum!(FriendshipStatus {
    Pending => "pending",
    Accepted => "accepted",
    Blocked => "blocked",
});

/// A directed row: `user_id` sent the request to `friend_id`.
#[derive(Debug, Clone, PartialEq)]
pub struct Friendship {
    pub user_id: Uuid,
    pub friend_id: Uuid,
    pub status: FriendshipStatus,
    pub created_at: DateTime<Utc>,
}

impl Friendship {
    pub fn other_than(&self, me: Uuid) -> Uuid {
        if self.user_id == me {
            self.friend_id
        } else {
            self.user_id
        }
    }
}

/// `between` holds the rows linking two users, in either direction.
pub fn are_friends(between: &[Friendship]) -> bool {
    between
        .iter()
        .any(|f| f.status == FriendshipStatus::Accepted)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RequestAction {
    Send,
    /// They already asked us, so asking back accepts: two people who both tap "add" end up friends.
    AcceptTheirs,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RequestRefused {
    ToSelf,
    AlreadyFriends,
    AlreadyRequested,
}

pub fn on_request(
    me: Uuid,
    them: Uuid,
    between: &[Friendship],
) -> Result<RequestAction, RequestRefused> {
    if me == them {
        return Err(RequestRefused::ToSelf);
    }
    if are_friends(between) {
        return Err(RequestRefused::AlreadyFriends);
    }
    if between.iter().any(|f| f.user_id == me) {
        return Err(RequestRefused::AlreadyRequested);
    }
    if between.is_empty() {
        Ok(RequestAction::Send)
    } else {
        Ok(RequestAction::AcceptTheirs)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(from: Uuid, to: Uuid, status: FriendshipStatus) -> Friendship {
        Friendship {
            user_id: from,
            friend_id: to,
            status,
            created_at: DateTime::UNIX_EPOCH,
        }
    }

    #[test]
    fn a_first_request_is_sent() {
        let (me, them) = (Uuid::new_v4(), Uuid::new_v4());
        assert_eq!(on_request(me, them, &[]), Ok(RequestAction::Send));
    }

    #[test]
    fn asking_yourself_is_refused() {
        let me = Uuid::new_v4();
        assert_eq!(on_request(me, me, &[]), Err(RequestRefused::ToSelf));
    }

    #[test]
    fn an_accepted_friendship_in_either_direction_is_refused() {
        let (me, them) = (Uuid::new_v4(), Uuid::new_v4());
        for rows in [
            [row(me, them, FriendshipStatus::Accepted)],
            [row(them, me, FriendshipStatus::Accepted)],
        ] {
            assert!(are_friends(&rows));
            assert_eq!(
                on_request(me, them, &rows),
                Err(RequestRefused::AlreadyFriends)
            );
        }
    }

    #[test]
    fn asking_twice_is_refused() {
        let (me, them) = (Uuid::new_v4(), Uuid::new_v4());
        let rows = [row(me, them, FriendshipStatus::Pending)];
        assert!(!are_friends(&rows));
        assert_eq!(
            on_request(me, them, &rows),
            Err(RequestRefused::AlreadyRequested)
        );
    }

    #[test]
    fn asking_someone_who_asked_you_accepts_their_request() {
        let (me, them) = (Uuid::new_v4(), Uuid::new_v4());
        let rows = [row(them, me, FriendshipStatus::Pending)];
        assert_eq!(on_request(me, them, &rows), Ok(RequestAction::AcceptTheirs));
        assert_eq!(rows[0].other_than(me), them);
        assert_eq!(rows[0].other_than(them), me);
    }
}
