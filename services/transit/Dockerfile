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

# Apply the Debian security patches that landed since the base tag was built:
# the tag tracks python releases, not Debian point updates, so perl-base and
# friends otherwise sit at whatever version shipped with the image.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 bledi \
    && useradd --system --uid 10001 --gid bledi --no-create-home --shell /usr/sbin/nologin bledi

COPY --from=builder /venv /venv

# The base image ships pip and setuptools system-wide, and setuptools vendors
# copies of wheel and jaraco.context that carry fixable HIGH advisories. The
# service never imports any of them -- it runs uvicorn from /venv -- so the
# whole system toolchain goes, which also shrinks the image.
RUN rm -rf /usr/local/lib/python3.11/site-packages/setuptools \
           /usr/local/lib/python3.11/site-packages/setuptools-*.dist-info \
           /usr/local/lib/python3.11/site-packages/pip \
           /usr/local/lib/python3.11/site-packages/pip-*.dist-info \
           /usr/local/lib/python3.11/site-packages/wheel \
           /usr/local/lib/python3.11/site-packages/wheel-*.dist-info \
           /usr/local/lib/python3.11/site-packages/pkg_resources \
           /usr/local/lib/python3.11/site-packages/_distutils_hack \
           /usr/local/lib/python3.11/site-packages/distutils-precedence.pth \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11 \
    && rm -rf /venv/lib/python3.11/site-packages/setuptools \
              /venv/lib/python3.11/site-packages/setuptools-*.dist-info \
              /venv/lib/python3.11/site-packages/pip \
              /venv/lib/python3.11/site-packages/pip-*.dist-info \
              /venv/lib/python3.11/site-packages/wheel \
              /venv/lib/python3.11/site-packages/wheel-*.dist-info \
              /venv/bin/pip /venv/bin/pip3 /venv/bin/pip3.11

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

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=30s \
  CMD ["curl", "-f", "http://localhost:8000/api/v1/health"]

CMD ["uvicorn", "--factory", "bledi_transit.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
