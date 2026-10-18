# Exact version tags plus the committed Cargo/npm lockfiles make the build
# inputs reviewable. The deploy operator records the resulting image digest;
# do not use Docker build arguments for any runtime secret.
FROM node:22.20.0-bookworm-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN UEC_PUBLIC_BUILD=true npm run build:public

FROM rust:1.90.0-bookworm AS api-builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked

FROM debian:bookworm-20261005-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && groupadd --gid 1000 render-secrets \
    && useradd --uid 65532 --gid nogroup --groups render-secrets --no-create-home --shell /usr/sbin/nologin uec \
    && rm -rf /var/lib/apt/lists/*
COPY --from=api-builder /app/target/release/uec-api /usr/local/bin/uec-api
COPY --from=frontend-builder /app/frontend/dist ./static
ENV PORT=8000
EXPOSE 8000
USER uec
CMD ["/usr/local/bin/uec-api"]
