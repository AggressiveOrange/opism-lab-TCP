#!/bin/bash
# Usage: lab-entry <auth|resolver|srv|student>
set -e
role="$1"

# Point the container at the lab resolver instead of Docker's embedded DNS (127.0.0.11).
if [ -n "$RESOLVER" ]; then
  printf 'nameserver %s\n' "$RESOLVER" > /etc/resolv.conf
fi

# Artificial latency on everything this container sends. Needs cap_add: NET_ADMIN and sch_netem.
if [ -n "$NETEM_DELAY" ]; then
  tc qdisc replace dev eth0 root netem delay "$NETEM_DELAY" \
    || echo "WARNING: netem not applied (missing NET_ADMIN or sch_netem module)" >&2
fi

case "$role" in
  auth)
    exec named -f -u bind -c /lab/named.conf
    ;;
  resolver)
    exec unbound -d -c /lab/unbound.conf
    ;;
  srv)
    mkdir -p /srv/www
    echo "hello" > /srv/www/small.txt
    head -c 20000000 /dev/zero > /srv/www/big.bin
    nginx -c /lab/nginx.conf
    for p in $(python3 -c 'import json; print(" ".join(str(s["iperf_port"]) for s in json.load(open("/lab/students.json"))))'); do
      iperf3 -s -p "$p" -D --logfile "/tmp/iperf3-$p.log"
    done
    exec python3 /usr/local/bin/srvd
    ;;
  student)
    named -u bind -c /lab/named.conf || echo "WARNING: named failed to start, see /var/log/named/named.log" >&2
    cd /lab/work
    exec ttyd -W -p 7681 -c "$TTYD_CRED" -t titleFixed="$STUDENT_ID" bash -l
    ;;
  *)
    echo "unknown role: $role" >&2; exit 1
    ;;
esac
