FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends asterisk && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/asterisk /var/log/asterisk /var/spool/asterisk /var/lib/asterisk \
    && chown -R asterisk:asterisk /var/run/asterisk /var/log/asterisk /var/spool/asterisk /var/lib/asterisk
# Run as the packaged asterisk user; the runtime dirs are pre-created above.
USER asterisk
CMD ["sh", "-c", "exec asterisk -f -vvv"]
