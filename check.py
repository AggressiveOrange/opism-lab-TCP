#!/usr/bin/env python3
"""Smoke-test the transport stand.

    python3 check.py --stand stand            # after start
    python3 check.py --stand stand --only s01

Every check runs inside the student's own container (docker compose exec), so it also proves
that the student can reach srv. Each line must start with OK.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stand", default="stand")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    stand = Path(args.stand)
    students = json.loads((stand / "students.json").read_text())
    if args.only:
        keep = set(args.only.split(","))
        students = [s for s in students if s["id"] in keep]
    compose = ["docker", "compose", "-f", str(stand / "compose.yaml")]

    def sh(service: str, cmd: str) -> str:
        p = subprocess.run(compose + ["exec", "-T", service, "bash", "-c", cmd], capture_output=True, text=True)
        return p.stdout + p.stderr

    srv_log = subprocess.run(compose + ["logs", "srv"], capture_output=True, text=True).stdout
    srvd = "srvd:" in srv_log and "iptables failed" not in srv_log
    print(f"{'OK  ' if srvd else 'FAIL'} srv: srvd and iptables rules" + ("" if srvd else " (docker compose -f stand/compose.yaml logs srv)"))
    bad = not srvd
    for s in students:
        sid = s["id"]
        res = {
            "dns": sh(sid, f"dig srv.{sid}.lab A +short +time=2 +tries=2").strip().splitlines()[-1:] == ["10.53.0.80"],
            "http": "server: srv:80" in sh(sid, "curl -s --max-time 5 http://10.53.0.80/"),
            "iperf": "receiver" in sh(sid, f"iperf3 -c 10.53.0.80 -p {s['iperf_port']} -t 1 2>&1"),
            "msg": "recv #" in sh(sid, "msg-client tcp"),
            "netem": "netem" in sh(sid, "tc qdisc show dev eth0"),
        }
        ok = all(res.values())
        bad |= not ok
        print(f"{'OK  ' if ok else 'FAIL'} {sid:<10} " + " ".join(f"{k}={'yes' if v else 'NO'}" for k, v in res.items()))
        cc = sh(sid, "sysctl -n net.ipv4.tcp_congestion_control").strip()
        print(f"     {sid:<10} tcp_congestion_control={cc}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
