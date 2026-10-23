#!/usr/bin/env python3
"""Let the API container reach a Nightshift Runtime tunnelled to this host's loopback.

Rootless Docker cannot reach the host's 127.0.0.1, but it can reach the host's
own LAN address. This forwards LISTEN_IP:PORT -> 127.0.0.1:TARGET and accepts
connections only from this host's own addresses (what container traffic looks
like after rootless NAT); anything else on the network is closed immediately.

    # on the laptop running Nightshift:
    ssh -N -R 127.0.0.1:18088:127.0.0.1:8088 user@server
    # on the server:
    python3 scripts/nightshift-forward.py 192.168.100.19 18089 18088
    # then METERLESS_BASE_URL=http://192.168.100.19:18089/v1 for the api container
"""

import socket
import sys
import threading

listen_ip, port, target = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
ALLOWED = {"127.0.0.1", listen_ip}


def pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while data := src.recv(65536):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client: socket.socket, peer: str) -> None:
    if peer not in ALLOWED:
        client.close()
        print(f"refused {peer}", flush=True)
        return
    try:
        upstream = socket.create_connection(("127.0.0.1", target), timeout=10)
    except OSError as exc:
        print(f"upstream down: {exc}", flush=True)
        client.close()
        return
    upstream.settimeout(None)
    threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
    pipe(upstream, client)


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind((listen_ip, port))
srv.listen(64)
print(f"forwarding {listen_ip}:{port} -> 127.0.0.1:{target}, accepting only {sorted(ALLOWED)}", flush=True)
while True:
    conn, (addr, _) = srv.accept()
    threading.Thread(target=handle, args=(conn, addr), daemon=True).start()
