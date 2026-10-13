# bledi.tn Rust backend Dockerfile
FROM rust:1.99-slim-bookworm AS builder

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
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

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user. The container needs no root privileges: it only
# reads its own binary and opens a TCP port > 1024.
RUN groupadd --system --gid 10001 bledi \
    && useradd --system --uid 10001 --gid bledi --no-create-home --shell /usr/sbin/nologin bledi

WORKDIR /app

COPY --from=builder /app/target/release/bledi-server /usr/local/bin/bledi-server
COPY rust/bledi-server/migrations /app/migrations

# NOTE: no DATABASE_URL default and no JWT_SECRET default are baked in.
# Both are REQUIRED at runtime and the server refuses to start without them.
# Supply them via `docker compose` env_file / environment, or `docker run -e`.
# Baking a default connection string into an image ships a working credential
# to anyone who pulls it.
ENV RUST_LOG=info

USER bledi

EXPOSE 3000

CMD ["bledi-server"]
