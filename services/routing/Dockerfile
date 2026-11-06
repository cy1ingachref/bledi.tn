# Build from the repository root (needs data/transport_map_corrected.json):
#   docker build -f services/routing/Dockerfile -t bledi-routing .
# If the build context is services/routing, copy the data file in separately
# or mount it at runtime via BLEDI_DATA_DIR.
FROM rust:1-bookworm AS builder
WORKDIR /build
COPY services/routing/Cargo.toml services/routing/Cargo.lock ./
COPY services/routing/src ./src
RUN cargo build --release --locked 2>/dev/null || cargo build --release

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 bledi \
    && useradd --system --uid 10001 --gid bledi --no-create-home --shell /usr/sbin/nologin bledi
COPY --from=builder /build/target/release/bledi-routing /usr/local/bin/bledi-routing
# Runtime graph data (single file the service reads; see src/graph.rs).
COPY data/transport_map_corrected.json /app/data/transport_map_corrected.json
ENV BLEDI_DATA_DIR=/app/data PORT=8081 RUST_LOG=info
USER bledi
EXPOSE 8081
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=20s \
  CMD ["curl", "-f", "http://localhost:8081/health"]
CMD ["bledi-routing"]
