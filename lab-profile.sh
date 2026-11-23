# Shell helpers for the transport lab (students' ttyd sessions).
if [ -n "$STUDENT_ID" ]; then
  export ZONE="$STUDENT_ID.lab"
  export SRV="srv.$STUDENT_ID.lab"
  # lab-loss 1%   add packet loss to everything this container sends (delay of the stand is kept)
  # lab-loss 0    remove the loss
  lab-loss() {
    if [ -z "$1" ]; then echo "використання: lab-loss <втрати, напр. 1%> | lab-loss 0"; return 1; fi
    if [ "$1" = 0 ] || [ "$1" = 0% ]; then
      tc qdisc change dev eth0 root netem delay "$NETEM_DELAY"
    else
      tc qdisc change dev eth0 root netem delay "$NETEM_DELAY" loss "$1"
    fi && tc -s qdisc show dev eth0 | sed -n '1,2p' | sed 's/delay [0-9.]*ms//'
  }
  # tcp-info [port]   short form of "ss -tin" for your connections to srv: one line per connection
  tcp-info() {
    ss -tinH dst 10.53.0.80 ${1:+"dport = :$1"} | paste - - | while read -r line; do
      printf '%s%s\n' "$(awk '{print $4, "->", $5}' <<<"$line")" \
        "$(grep -oE ' (cubic|bbr|reno) | (rtt|cwnd|ssthresh|bytes_acked|snd_wnd):[^ ]+| (rwnd|cwnd|sndbuf)_limited:[^ ]+' <<<"$line" | tr -d '\n')"
    done
  }
  [[ $- == *i* ]] && cat <<EOF

  Стенд «Транспортний рівень». Ідентифікатор: $STUDENT_ID   Ваш вузол: $STUDENT_IP
  Резолвер: 10.53.0.53   Віддалений сервер: \$SRV = $SRV (10.53.0.80)

  \$IPERF_PORT    ваш порт iperf3 на сервері: $IPERF_PORT
  msg-client     клієнт сервера повідомлень (завдання 4): msg-client tcp | msg-client udp
  lab-loss       втрати на вихідному інтерфейсі: lab-loss 1% | lab-loss 0
  tcp-info       скорочений вивід ss -tin для ваших з'єднань із srv: tcp-info [порт]

  Робочий каталог (зберігається між перезапусками): /lab/work

EOF
fi
