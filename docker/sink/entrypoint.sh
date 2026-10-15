#!/bin/sh
set -eu

: "${SINK_IP:?SINK_IP must be set}"

HTTP_LOG=/var/log/skill-warden-http.log
: > "${HTTP_LOG}"

cat > /etc/dnsmasq.conf <<EOF
no-resolv
no-hosts
no-poll
listen-address=${SINK_IP}
bind-interfaces
log-queries
log-facility=-
address=/#/${SINK_IP}
EOF

python3 /http_catchall.py &
HTTP_PID=$!

cleanup() {
  kill "${HTTP_PID}" 2>/dev/null || true
}
trap cleanup EXIT

exec dnsmasq --keep-in-foreground --conf-file=/etc/dnsmasq.conf
