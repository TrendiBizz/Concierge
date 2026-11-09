FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends asterisk && rm -rf /var/lib/apt/lists/*
# The package creates the asterisk user and gives it /var/lib, /var/log, /var/run and /var/spool/asterisk. Config files are
# mounted read-only by compose, and SIP/RTP use ports above 1024, so nothing here needs root.
USER asterisk
CMD ["asterisk", "-f", "-vvv"]
