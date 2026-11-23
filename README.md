# Transport layer lab stand (ОПІСМ, Topic 6)

Same layout as the DNS and TLS stands: one Docker image, one generated compose file, one container per student.

    docker build -t tplab:latest image/
    cp students.example.csv students.csv   # then edit: one row per student
    python3 gen.py students.csv --out stand
    cd stand && docker compose up -d && cd ..
    python3 check.py --stand stand

Student mode (Codespaces, repository root): `python3 gen.py --student <id> --salt opism-2026`, then `./up.sh`.
`up.sh` builds the image if needed and stops the DNS and TLS stands first: all of them use 10.53.0.0/16.

Files:
- image/        Dockerfile, entrypoint (roles: auth, resolver, srv, student), srvd.py, msg-client, shell helpers
- templates/    Jinja2 templates for every config, the student zone, srv nginx config and the variant card
- gen.py        students.csv -> stand/ (configs, compose.yaml, cards/, instructor/answers.csv)
- check.py      smoke test, run from inside each student's container
- up.sh         start + Codespaces iptables fix + smoke test
- лб3-транспорт-методичка.md, лб3-транспорт-бланк.md   for students

Stand:
- root, tld, resolver-a: DNS hierarchy as in the DNS lab; student zones are pre-filled (srv.<id>.lab -> 10.53.0.80).
- srv (10.53.0.80), needs NET_ADMIN for its own iptables rules:
  - nginx on port 80: HTTP/1.1 keep-alive, files small.txt and big.bin (20 MB);
  - srvd on port 8080: HTTP/1.0 without Content-Length, so the server always closes first;
  - srvd on the five fault ports of each student (20000 + 10*row + slot): ok, reset, hang
    are served by srvd, closed has no listener, icmp and drop are iptables rules;
  - srvd on 9000 TCP and UDP: message server, the student's words one send()/datagram each;
  - UDP 5398 dropped by iptables, UDP 5399 without a listener;
  - one iperf3 server per student on 5200 + row.
- student: own zone (BIND), ttyd; netem delay of the variant on eth0 (needs NET_ADMIN and
  sch_netem on the host; the smoke test reports netem=NO otherwise). Helpers: lab-loss, tcp-info, msg-client.

Variants: gen.py variant(id, salt). Faults per student: drop, hang, ok plus 2 of {closed, icmp, reset},
shuffled over the five ports. Delay 20-50 ms, window for task 5 from {32768, 65536, 131072},
loss for task 6 from {0.5%, 1%, 2%}, 3-5 message words. Instructor answers: stand/instructor/answers.csv.

Never edit files in stand/ by hand; regenerate instead. Student zone files and */work are never overwritten.

Not verified: the stand with netem (the build host kernel had no sch_netem). Delay-dependent values in the
key were checked with a user-space relay in network namespaces; compare the first Codespaces reports with the key.
