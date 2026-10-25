"""Host-side HTTP CONNECT proxy restricted to RouterAI and Wi-Fi egress."""

from __future__ import annotations

import base64
import os
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .wifi_egress import ensure_routerai_wifi_routes


class RouterAIProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:
        return

    def do_CONNECT(self) -> None:
        requested = urlsplit("//" + self.path)
        host, port = requested.hostname, requested.port or 443
        if host != "routerai.ru" or port != 443:
            self.send_error(403, "Proxy is restricted to RouterAI HTTPS")
            return
        expected = "Basic " + base64.b64encode(
            f"{os.environ['ROUTERAI_PROXY_USER']}:{os.environ['ROUTERAI_PROXY_PASSWORD']}".encode()
        ).decode()
        if self.headers.get("Proxy-Authorization") != expected:
            self.send_response(407, "Proxy Authentication Required")
            self.send_header("Proxy-Authenticate", 'Basic realm="RouterAI Wi-Fi egress"')
            self.end_headers()
            return
        try:
            route = ensure_routerai_wifi_routes(host)
            source = str(route["source_ipv4"])
            upstream = socket.create_connection((host, port), timeout=20, source_address=(source, 0))
        except Exception:
            self.send_error(502, "Wi-Fi egress route unavailable")
            return
        self.send_response(200, "Connection Established")
        self.end_headers()
        self.connection.setblocking(True)
        upstream.setblocking(True)
        sockets = (self.connection, upstream)
        try:
            while True:
                readable, _, exceptional = select.select(sockets, (), sockets, 60)
                if exceptional or not readable:
                    break
                for source_socket in readable:
                    target_socket = upstream if source_socket is self.connection else self.connection
                    data = source_socket.recv(65536)
                    if not data:
                        return
                    target_socket.sendall(data)
        except (OSError, ValueError):
            pass
        finally:
            upstream.close()


def serve() -> None:
    if not os.getenv("ROUTERAI_PROXY_USER") or not os.getenv("ROUTERAI_PROXY_PASSWORD"):
        raise RuntimeError("ROUTERAI_PROXY_USER and ROUTERAI_PROXY_PASSWORD are required")
    route = ensure_routerai_wifi_routes("routerai.ru")
    host = os.getenv("ROUTERAI_PROXY_BIND", "0.0.0.0")
    port = int(os.getenv("ROUTERAI_PROXY_PORT", "18128"))
    server = ThreadingHTTPServer((host, port), RouterAIProxyHandler)
    server.daemon_threads = True
    print(f"RouterAI-only egress proxy ready on {host}:{port} via {route['interface_alias']}")
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    serve()
