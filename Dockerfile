# bledi.tn Rust backend Dockerfile
FROM rust:1.80-slim-bookworm AS builder

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    pkg-config libssl-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests
COPY rust/Cargo.toml rust/Cargo.lock* ./
COPY rust/bledi-core/Cargo.toml bledi-core/
COPY rust/bledi-server/Cargo.toml bledi-server/

# Create dummy main files to compile dependencies
RUN mkdir -p bledi-core/src bledi-server/src \
    && echo "pub fn placeholder() {}" > bledi-core/src/lib.rs \
    && echo "fn main() {}" > bledi-server/src/main.rs

# Build dependencies (cached layer)
RUN cargo build --release || true

# Copy actual source
COPY rust/bledi-core/src bledi-core/src
COPY rust/bledi-server/src bledi-server/src
COPY rust/bledi-server/migrations bledi-server/migrations

# Build
RUN touch bledi-core/src/lib.rs bledi-server/src/main.rs \
    && cargo build --release

# Runtime image
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/target/release/bledi-server /usr/local/bin/bledi-server
COPY rust/bledi-server/migrations /app/migrations

ENV DATABASE_URL=postgres://postgres:postgres@localhost:5432/bledi
ENV RUST_LOG=info

EXPOSE 3000

CMD ["bledi-server"]
