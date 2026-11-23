#!/usr/bin/env python3
"""Generate the transport-layer lab stand from students.csv.

Usage:
    python3 gen.py --student sNN                    # student mode (Codespaces): one-student stand in ./stand
    python3 gen.py students.csv                     # instructor mode: whole group
    python3 gen.py students.csv --out stand --salt opism-2026

CSV columns: id,name[,password]
    id        short lowercase label, used as zone name: s01 -> s01.lab
    name      student name, only printed on the variant card
    password  ttyd password; generated if empty

Row order defines IP (10.53.1.<row>), terminal port (7000+<row>), the student's fault ports
(20000+10*<row>+k) and iperf3 port (5200+<row>): append new students at the end, never reorder rows.

Student zone and work/ are NEVER overwritten.
"""
import argparse
import csv
import json
import random
import re
import secrets
import string
import sys
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).resolve().parent
# Faults behind the five diagnosis ports: "drop" and "hang" are always present (task 3 compares the
# two timeouts and asks about the ACK), two of the other three are drawn, plus one healthy port.
# Any two of the three include "closed" or "icmp", so every variant has a refused connection.
FAULTS = ["closed", "icmp", "reset"]
DELAYS = [20, 25, 30, 35, 40, 45, 50]        # ms, netem on the student's eth0 = RTT to any stand node
WINDOWS = [32768, 65536, 131072]             # bytes, iperf3 -w in task 5
LOSSES = ["0.5%", "1%", "2%"]                # netem loss in task 6
WORDS = ["ALFA", "BRAVO", "DELTA", "ECHO", "GOLF", "HOTEL", "KILO", "LIMA", "OSCAR", "TANGO", "VICTOR", "ZULU"]


def variant(sid: str, salt: str) -> dict:
    """Deterministic per-student parameters: same id + salt -> same variant."""
    r = random.Random(f"{salt}:tcp:{sid}")
    faults = r.sample(FAULTS, 2) + ["drop", "hang", "ok"]
    r.shuffle(faults)
    slots = r.sample(range(10), 5)           # which of the 10 ports of the student's block are used
    return {
        "delay": r.choice(DELAYS),
        "window": r.choice(WINDOWS),
        "loss": r.choice(LOSSES),
        "faults": faults,                    # faults[i] is served on port p{i+1}
        "slots": slots,
        "messages": r.sample(WORDS, r.randint(3, 5)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", help="roster CSV (instructor mode)")
    ap.add_argument("--student", help="student mode: build a one-student stand for this id, without instructor files")
    ap.add_argument("--out", default="stand")
    ap.add_argument("--salt", default="opism-2026", help="change it per group/semester to get new variants")
    ap.add_argument("--bind-addr", default="0.0.0.0", help="host address for ttyd ports (127.0.0.1 behind a reverse proxy)")
    args = ap.parse_args()

    out = Path(args.out)
    env = Environment(loader=FileSystemLoader(HERE / "templates"), undefined=StrictUndefined,
                      keep_trailing_newline=True)
    serial_date = time.strftime("%Y%m%d")
    serial_now = int(time.time())

    if bool(args.csv) == bool(args.student):
        sys.exit("give either a roster CSV or --student <id>")
    if args.student:
        rows = [{"id": args.student, "name": "", "password": ""}]
    else:
        with open(args.csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    students = []
    for n, row in enumerate(rows, start=1):
        sid = (row.get("id") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,9}", sid):
            sys.exit(f"row {n}: bad id {sid!r} (lowercase, starts with a letter, max 10 chars)")
        if n > 250:
            sys.exit("more than 250 students: extend the IP plan first")
        pw = (row.get("password") or "").strip() or "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
        s = {"id": sid, "name": (row.get("name") or "").strip(), "password": pw,
             "ip": f"10.53.1.{n}", "port": 7000 + n, "iperf_port": 5200 + n}
        s.update(variant(sid, args.salt))
        s["fault_ports"] = [20000 + 10 * n + k for k in s["slots"]]
        s["show_password"] = bool(args.student)
        students.append(s)
    ids = [s["id"] for s in students]
    if len(set(ids)) != len(ids):
        sys.exit("duplicate ids in CSV")

    def write(path: Path, text: str, mode: int = 0o644, keep: bool = False) -> None:
        if keep and path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)

    named = env.get_template("named.conf.j2")
    write(out / "root/named.conf", named.render(comment="root", zone=".", file="/lab/root.zone"))
    write(out / "root/root.zone", env.get_template("root.zone.j2").render(serial=serial_now))
    write(out / "tld/named.conf", named.render(comment="TLD lab.", zone="lab", file="/lab/lab.zone"))
    write(out / "tld/lab.zone", env.get_template("tld.zone.j2").render(serial=serial_now, students=students))
    write(out / "resolver-a/unbound.conf", env.get_template("unbound.conf.j2").render(name="resolver-a"))
    write(out / "resolver-a/root.hints", (HERE / "templates/root.hints").read_text())
    write(out / "srv/nginx.conf", env.get_template("srv-nginx.conf.j2").render())
    write(out / "srv/students.json", json.dumps(
        [{k: s[k] for k in ("id", "ip", "iperf_port", "faults", "fault_ports", "messages")} for s in students],
        ensure_ascii=False, indent=1))

    for s in students:
        d = out / "students" / s["id"]
        write(d / "named.conf", named.render(comment=f"student {s['id']}", zone=f"{s['id']}.lab",
                                             file=f"/lab/zone/{s['id']}.lab.zone"))
        write(d / "zone" / f"{s['id']}.lab.zone",
              env.get_template("student.zone.j2").render(s=s, serial=serial_date), keep=True)
        (d / "work").mkdir(parents=True, exist_ok=True)
        (d / "work").chmod(0o777)
        (d / "zone").chmod(0o755)
        write(out / "cards" / f"{s['id']}.md", env.get_template("card.md.j2").render(s=s))

    write(out / "compose.yaml", env.get_template("compose.yaml.j2").render(
        students=students, bind_addr=args.bind_addr))
    (out / "students.json").write_text(json.dumps(
        [{k: s[k] for k in ("id", "ip", "iperf_port", "fault_ports")} for s in students]))
    if args.student:
        print(f"student stand for {args.student} in {out}/; card: {out}/cards/{args.student}.md")
        return
    (out / "instructor").mkdir(parents=True, exist_ok=True)
    with open(out / "instructor/credentials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "port", "login", "password"])
        for s in students:
            w.writerow([s["id"], s["name"], s["port"], s["id"], s["password"]])
    with open(out / "instructor/answers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "delay_ms", "window", "loss", "p1", "p2", "p3", "p4", "p5",
                    "port1", "port2", "port3", "port4", "port5", "messages"])
        for s in students:
            w.writerow([s["id"], s["delay"], s["window"], s["loss"], *s["faults"], *s["fault_ports"],
                        " ".join(s["messages"])])
    (out / "instructor/variants.json").write_text(json.dumps(students, ensure_ascii=False, indent=1))
    print(f"generated {len(students)} students in {out}/")


if __name__ == "__main__":
    main()
