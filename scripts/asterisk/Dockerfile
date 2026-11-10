FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends asterisk && rm -rf /var/lib/apt/lists/*
# Asterisk's control socket and pid live under /run, which is a tmpfs at run time.
# The non-root `asterisk` user cannot create that directory, so the first build
# started without a CLI socket. Create it at start and run the daemon; the
# container is reachable only on the private phone network (no published ports).
CMD ["sh", "-c", "mkdir -p /var/run/asterisk && exec asterisk -f -vvv"]
