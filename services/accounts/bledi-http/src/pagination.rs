use serde::Deserialize;

#[derive(Debug, Deserialize, Default)]
pub struct Pagination {
    #[serde(default)]
    pub limit: Option<usize>,
    #[serde(default)]
    pub offset: Option<usize>,
}

impl From<Pagination> for (usize, usize) {
    fn from(value: Pagination) -> Self {
        let limit = value.limit.unwrap_or(20).clamp(1, 200);
        let offset = value.offset.unwrap_or(0);
        (limit, offset)
    }
}
