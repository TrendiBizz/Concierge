FROM rust:1.99-bookworm AS builder
WORKDIR /app
COPY Cargo.toml ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --shell /usr/sbin/nologin app
COPY --from=builder --chown=app:app /app/target/release/email-auth /usr/local/bin/email-auth
USER app
EXPOSE 8090
ENV MAX_BYTES=512000
CMD ["email-auth"]
