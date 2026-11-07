# Isolated Rust social service. Uses the API container's network namespace
# in Compose, so its 127.0.0.1 listener cannot be reached from the internet.
FROM rust:1.91-bookworm AS build
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --locked --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10002 social \
    && mkdir -p /data && chown social:social /data
COPY --from=build /build/target/release/concierge-social /usr/local/bin/concierge-social
USER social
ENV SOCIAL_DB=/data/social.db \
    SOCIAL_BIND=127.0.0.1:4390 \
    SOCIAL_ENABLE_PUBLISH=false
ENTRYPOINT ["/usr/local/bin/concierge-social"]
