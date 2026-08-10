# Argus — production image (Phase 9)
# Multi-stage: build deps in a fat stage, ship a slim runtime.
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --prefix=/install .


FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="argus" \
      org.opencontainers.image.description="Argus AI agent framework" \
      org.opencontainers.image.licenses="MIT"

# Non-root user. Agents running capabilities should not be root.
RUN useradd --create-home --uid 10001 argus

# Copy the installed package from the builder stage.
COPY --from=builder /install /usr/local

# Volumes: observability store + vault live here.
VOLUME ["/data"]

WORKDIR /data

USER argus

ENTRYPOINT ["argus"]
CMD ["--help"]
