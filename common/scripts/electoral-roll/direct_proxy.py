"""Run a local HTTPS proxy that sends connections out through one chosen network interface."""

import json
import select
import socket
import socketserver
import ssl
import threading
import time
import urllib.parse

DOH = "1.1.1.1"
_cache = {}  # Maps host to (address, expires_at).


def bound_socket(interface):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
    s.settimeout(30)
    return s


def resolve(host, interface):
    address, expires_at = _cache.get(host, (None, 0))
    if address and time.time() < expires_at:
        return address
    s = bound_socket(interface)
    s.connect((DOH, 443))
    with ssl.create_default_context().wrap_socket(s, server_hostname=DOH) as tls:
        query = urllib.parse.urlencode({"name": host, "type": "A"})
        tls.sendall(f"GET /dns-query?{query} HTTP/1.1\r\nHost: {DOH}\r\n"
                    "Accept: application/dns-json\r\nConnection: close\r\n\r\n".encode())
        reply = b""
        while chunk := tls.recv(65536):
            reply += chunk
    answers = [a for a in json.loads(reply.split(b"\r\n\r\n", 1)[1]).get("Answer", []) if a["type"] == 1]
    if not answers:
        raise OSError(f"no address found for {host}")
    _cache[host] = (answers[0]["data"], time.time() + answers[0]["TTL"])
    return answers[0]["data"]


def pipe(a, b, idle=300):
    a.settimeout(None)
    b.settimeout(None)
    while True:
        ready, _, _ = select.select([a, b], [], [], idle)
        if not ready:
            return
        for src in ready:
            data = src.recv(65536)
            if not data:
                return
            (b if src is a else a).sendall(data)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        request = self.rfile.readline(8192).split()
        while self.rfile.readline(8192) not in (b"\r\n", b"\n", b""):
            pass  # Skip the request headers, which are not needed.
        if len(request) < 2 or request[0] != b"CONNECT":
            self.wfile.write(b"HTTP/1.1 501 Only CONNECT is supported\r\n\r\n")
            return
        host, port = request[1].decode().rsplit(":", 1)
        try:
            upstream = bound_socket(self.server.interface)
            upstream.connect((resolve(host, self.server.interface), int(port)))
        except OSError:
            self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        with upstream:
            self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            pipe(self.connection, upstream)


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self, interface):
        self.interface = interface
        super().__init__(("127.0.0.1", 0), Handler)


def start_proxy(interface):
    """Serve the proxy on a free local port in a background thread and return its URL."""
    server = Server(interface)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"
