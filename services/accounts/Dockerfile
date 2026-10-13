# bledi.tn Rust backend Dockerfile
FROM rust:1.99-slim-bookworm AS builder

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config libssl-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests
COPY Cargo.toml Cargo.lock* ./
COPY bledi-domain/Cargo.toml bledi-domain/
COPY bledi-application/Cargo.toml bledi-application/
COPY bledi-postgres/Cargo.toml bledi-postgres/
COPY bledi-http/Cargo.toml bledi-http/
COPY bledi-server/Cargo.toml bledi-server/

# Create dummy sources to compile dependencies
RUN for crate in bledi-domain bledi-application bledi-postgres bledi-http; do \
        mkdir -p $crate/src && echo "pub fn placeholder() {}" > $crate/src/lib.rs; \
    done \
    && mkdir -p bledi-server/src && echo "fn main() {}" > bledi-server/src/main.rs

# Build dependencies (cached layer)
RUN cargo build --release || true

# Copy actual source. The migrations are embedded into the binary at compile time.
COPY bledi-domain/src bledi-domain/src
COPY bledi-application/src bledi-application/src
COPY bledi-postgres/src bledi-postgres/src
COPY bledi-http/src bledi-http/src
COPY bledi-server/src bledi-server/src
COPY migrations migrations

# Build
RUN touch */src/*.rs \
    && cargo build --release -p bledi-server

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

# NOTE: no DATABASE_URL default and no JWT_SECRET default are baked in.
# Both are REQUIRED at runtime and the server refuses to start without them.
# Supply them via `docker compose` env_file / environment, or `docker run -e`.
# Baking a default connection string into an image ships a working credential
# to anyone who pulls it.
ENV RUST_LOG=info

USER bledi

EXPOSE 3000

CMD ["bledi-server"]
