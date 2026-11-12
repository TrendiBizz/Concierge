#!/usr/bin/env bash
# Host hardening for the Trendi Concierge VPS. Idempotent: safe to re-run.
# Run ON the VPS as root:  bash harden_host.sh
#
# What it does (and how to undo each part):
#  1. SIP signalling (udp/5060) restricted to the Hero ranges via DOCKER-USER
#     (Docker bypasses ufw). RTP 10000-10099 is deliberately left open so a
#     media gateway on another address can never cause one-way audio.
#     Undo: iptables -D DOCKER-USER -p udp -m conntrack --ctstate DNAT \
#              --ctorigdstport 5060 -j TRENDI-SIP ; systemctl disable --now trendi-sip-firewall
#  2. IPv6 udp/5060 dropped (Hero is IPv4-only).
#  3. Container log rotation (logrotate copytruncate) + docker default log caps.
#  4. sshd: X11 off, MaxAuthTries 3, root key-only, validated before reload.
#  5. fail2ban: sshd jail with 1 h ban after 3 failures, plus recidive jail.
set -euo pipefail

HERO_NETS="${HERO_NETS:-103.212.52.0/24}"   # space separated; override via env
STAMP="$(date +%Y%m%d-%H%M%S)"
BK="/opt/trendi/backups/harden-${STAMP}"
mkdir -p "$BK"

echo "== backup current state to $BK"
iptables-save > "$BK/iptables.save" || true
ip6tables-save > "$BK/ip6tables.save" || true
cp -a /etc/ssh/sshd_config /etc/ssh/sshd_config.d "$BK/" 2>/dev/null || true
cp -a /etc/fail2ban "$BK/fail2ban" 2>/dev/null || true
cp -a /etc/docker "$BK/docker" 2>/dev/null || true

echo "== 1. SIP firewall script + systemd unit"
cat > /usr/local/sbin/trendi-sip-firewall.sh <<EOF
#!/usr/bin/env bash
# Applied after docker.service so DOCKER-USER exists. Idempotent.
set -e
iptables -N TRENDI-SIP 2>/dev/null || true
iptables -F TRENDI-SIP
for net in ${HERO_NETS}; do iptables -A TRENDI-SIP -s "\$net" -j RETURN; done
iptables -A TRENDI-SIP -j DROP
iptables -N DOCKER-USER 2>/dev/null || true
# Remove any previous copy of the jump, then insert at the top.
while iptables -C DOCKER-USER -p udp -m conntrack --ctstate DNAT --ctorigdstport 5060 -j TRENDI-SIP 2>/dev/null; do
  iptables -D DOCKER-USER -p udp -m conntrack --ctstate DNAT --ctorigdstport 5060 -j TRENDI-SIP
done
iptables -I DOCKER-USER 1 -p udp -m conntrack --ctstate DNAT --ctorigdstport 5060 -j TRENDI-SIP
# IPv6: Hero is IPv4-only, so drop signalling and media probes over v6.
ip6tables -C INPUT -p udp --dport 5060 -j DROP 2>/dev/null || ip6tables -I INPUT 1 -p udp --dport 5060 -j DROP
ip6tables -C INPUT -p udp --dport 10000:10099 -j DROP 2>/dev/null || ip6tables -I INPUT 1 -p udp --dport 10000:10099 -j DROP
EOF
chmod 755 /usr/local/sbin/trendi-sip-firewall.sh

cat > /etc/systemd/system/trendi-sip-firewall.service <<'EOF'
[Unit]
Description=Restrict SIP signalling to the carrier (Docker bypasses ufw)
After=docker.service network-online.target
Wants=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/trendi-sip-firewall.sh

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable trendi-sip-firewall.service >/dev/null
/usr/local/sbin/trendi-sip-firewall.sh
echo "   DOCKER-USER now:"; iptables -S DOCKER-USER; iptables -S TRENDI-SIP

echo "== 3. log rotation"
cat > /etc/logrotate.d/docker-containers <<'EOF'
/var/lib/docker/containers/*/*-json.log {
    size 100M
    rotate 3
    compress
    delaycompress
    missingok
    copytruncate
}
EOF
mkdir -p /etc/docker
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "3" }
}
EOF
  echo "   wrote /etc/docker/daemon.json (applies to containers on next recreate; docker NOT restarted)"
fi
# Shrink the existing oversized PBX log now, keeping the most recent lines.
PBXLOG="$(docker inspect -f '{{.LogPath}}' asterisk-pbx-1 2>/dev/null || true)"
if [ -n "$PBXLOG" ] && [ -f "$PBXLOG" ]; then
  SIZE=$(stat -c %s "$PBXLOG")
  if [ "$SIZE" -gt 209715200 ]; then
    tail -c 20000000 "$PBXLOG" > "$BK/pbx-log-tail.json" || true
    : > "$PBXLOG"
    echo "   truncated PBX log (was $((SIZE/1048576)) MB); tail kept in $BK"
  fi
fi
/usr/sbin/logrotate -f /etc/logrotate.d/docker-containers || true

echo "== 4. sshd"
cat > /etc/ssh/sshd_config.d/00-trendi-hardening.conf <<'EOF'
# sshd honours the FIRST value seen, so this file sorts before 50-cloud-init.conf.
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 20
ClientAliveInterval 300
ClientAliveCountMax 2
EOF
sshd -t && systemctl reload ssh && echo "   sshd reloaded OK" || { echo "   sshd config INVALID, removing"; rm -f /etc/ssh/sshd_config.d/00-trendi-hardening.conf; }

echo "== 5. fail2ban"
cat > /etc/fail2ban/jail.d/trendi.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 3

[sshd]
enabled = true

[recidive]
enabled  = true
bantime  = 1w
findtime = 1d
maxretry = 3
EOF
systemctl restart fail2ban
sleep 2
fail2ban-client status | sed -n 1,4p

echo "== verification"
docker exec asterisk-pbx-1 asterisk -rx "pjsip show registrations" | grep -i "concierge-reg" || echo "!! registration line missing"
echo "Backups: $BK"
echo "DONE"
