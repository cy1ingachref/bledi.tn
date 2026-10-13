# Build from the repository root, which holds the shared data directory:
#   docker build -f services/transit/Dockerfile .
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build
COPY services/transit/requirements.lock.txt .
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock.txt
COPY services/transit/pyproject.toml .
COPY services/transit/src src
RUN /venv/bin/pip install --no-cache-dir --no-deps .

FROM python:3.11-slim-bookworm

RUN groupadd --system --gid 10001 bledi \
    && useradd --system --uid 10001 --gid bledi --no-create-home --shell /usr/sbin/nologin bledi

COPY --from=builder /venv /venv
# Only what the service reads. road_graph.npz is not committed (153 MB): mount
# it and set ROAD_GRAPH_PATH, otherwise road legs fall back to the caches.
COPY data/seed_all_tunisia_routes.tagged.json \
     data/seed_routes_destination_tunis.json \
     data/route_geometry.json \
     data/walk_geometry.json \
     data/taxi_geometry.json \
     data/map_rail.geojson \
     data/map_roads.geojson \
     data/louage_links.json \
     data/rail_graph.npz \
     /app/data/

ENV PATH=/venv/bin:$PATH \
    BLEDI_DATA_DIR=/app/data \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER bledi
EXPOSE 8000

CMD ["uvicorn", "--factory", "bledi_transit.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
