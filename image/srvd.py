#!/usr/bin/env python3
"""srv daemon of the transport lab.

Reads /lab/students.json and serves, per student:
  fault ports  ok     accepts, answers one HTTP-like line, closes
               reset  accepts, reads the request, aborts the connection with RST
               hang   accepts and never reads: the kernel still acknowledges the request
               closed nothing listens: the kernel answers SYN with RST
               icmp   iptables REJECT with icmp-port-unreachable
               drop   iptables DROP: no answer at all
  port 8080 HTTP/1.0 without Content-Length: the server closes first (task 2)
  port 9000 TCP and UDP: message server (task 4)
      TCP: on connect sends the student's messages, one send() each, TCP_NODELAY
      UDP: on any datagram replies with the same messages, one datagram each
UDP 5398 is dropped by iptables and nothing listens on UDP 5399 (task 4).
"""
import asyncio
import json
import socket
import struct
import subprocess
import sys

STUDENTS = json.load(open("/lab/students.json"))
BY_IP = {s["ip"]: s for s in STUDENTS}


def ipt(*rule: str) -> None:
    subprocess.run(["iptables", "-A", "INPUT", *rule], check=True)


def firewall() -> None:
    subprocess.run(["iptables", "-F", "INPUT"], check=True)
    ipt("-p", "udp", "--dport", "5398", "-j", "DROP")
    for s in STUDENTS:
        for kind, port in zip(s["faults"], s["fault_ports"]):
            if kind == "drop":
                ipt("-p", "tcp", "--dport", str(port), "-j", "DROP")
            elif kind == "icmp":
                ipt("-p", "tcp", "--dport", str(port), "-j", "REJECT", "--reject-with", "icmp-port-unreachable")


async def ok(reader, writer):
    try:
        await asyncio.wait_for(reader.readline(), 5)
    except Exception:
        pass
    writer.write(b"HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nserver: srv, port open\n")
    await writer.drain()
    writer.close()


async def reset(reader, writer):
    try:
        await asyncio.wait_for(reader.read(4096), 5)
    except Exception:
        pass
    sock = writer.get_extra_info("socket")
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    writer.transport.abort()


HANGING = []


async def hang(reader, writer):
    # Never read, never answer, keep the socket open for 10 minutes.
    HANGING.append(writer)
    await asyncio.sleep(600)
    writer.transport.abort()


async def close_first(reader, writer):
    # HTTP/1.0 without Content-Length: the client learns where the body ends only from FIN,
    # so the server always closes first and keeps TIME_WAIT.
    try:
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    except Exception:
        pass
    peer = writer.get_extra_info("peername")
    writer.write(f"HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nserver: srv:8080\nclient: {peer[0]}:{peer[1]}\n".encode())
    await writer.drain()
    writer.close()


async def messages(reader, writer):
    peer = writer.get_extra_info("peername")[0]
    s = BY_IP.get(peer)
    words = s["messages"] if s else ["UNKNOWN"]
    sock = writer.get_extra_info("socket")
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    for i, w in enumerate(words, 1):
        writer.write(f"{i}:{w};".encode())
        await writer.drain()
        await asyncio.sleep(0.02)
    await asyncio.sleep(1)
    writer.close()


class UdpMessages(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.t = transport

    def datagram_received(self, data, addr):
        s = BY_IP.get(addr[0])
        words = s["messages"] if s else ["UNKNOWN"]
        for i, w in enumerate(words, 1):
            self.t.sendto(f"{i}:{w};".encode(), addr)


async def main() -> None:
    firewall()
    handlers = {"ok": ok, "reset": reset, "hang": hang}
    servers = []
    for s in STUDENTS:
        for kind, port in zip(s["faults"], s["fault_ports"]):
            if kind in handlers:
                servers.append(await asyncio.start_server(handlers[kind], "0.0.0.0", port, backlog=64))
    servers.append(await asyncio.start_server(messages, "0.0.0.0", 9000))
    servers.append(await asyncio.start_server(close_first, "0.0.0.0", 8080, backlog=256))
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(UdpMessages, local_addr=("0.0.0.0", 9000))
    print(f"srvd: {len(servers)} TCP listeners for {len(STUDENTS)} students", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except subprocess.CalledProcessError as e:
        sys.exit(f"srvd: iptables failed: {e}")
