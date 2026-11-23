# One image for every role on the transport stand: root, TLD, resolver, srv, student.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bind9 bind9-utils bind9-dnsutils unbound nginx ttyd \
      iperf3 python3 iptables \
      curl tcpdump iproute2 nano vim-tiny less ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && rndc-confgen -a -k rndc-key -c /etc/bind/rndc.key \
 && chown bind:bind /etc/bind/rndc.key \
 && mkdir -p /var/log/named /run/named \
 && chown bind:bind /var/log/named /run/named
COPY entrypoint.sh /usr/local/bin/lab-entry
COPY srvd.py /usr/local/bin/srvd
COPY msg-client /usr/local/bin/msg-client
COPY lab-profile.sh /etc/profile.d/lab.sh
RUN chmod +x /usr/local/bin/lab-entry /usr/local/bin/srvd /usr/local/bin/msg-client
ENTRYPOINT ["/usr/local/bin/lab-entry"]
