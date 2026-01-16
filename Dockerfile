# Build stage
FROM rust:1-bookworm AS builder

WORKDIR /app
COPY . .
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

WORKDIR /app

# Install necessary runtime dependencies (e.g. ca-certificates for HTTPS)
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*

# Copy the binary from the builder stage
COPY --from=builder /app/target/release/heatmap-backend .

# Copy the static assets folder for frontend serving
COPY static static

# Environment configuration
ENV PORT=8000
EXPOSE 8000

CMD ["./heatmap-backend"]
