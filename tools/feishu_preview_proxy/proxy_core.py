"""Core runtime for the local Feishu HTTPS CONNECT proxy.

This module owns configuration, JSON event logging, PAC generation, and the
server loop. HTTP byte handling and certificate generation live in sibling
modules so each concern stays small and independently testable.
"""
from __future__ import annotations

import json
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from proxy_certs import ensure_certs
from proxy_http import (
    BufferedSocket,
    add_cors_headers,
    forward_response_body,
    header_value,
    read_request,
    read_response_head,
    rewrite_request,
    safe_headers,
)

MAX_LOG_BYTES = 5 * 1024 * 1024


class Config(TypedDict, total=False):
    listen_host: str
    listen_port: int
    pac_port: int
    upstream_port: int
    max_workers: int
    connect_timeout: int
    read_timeout: int
    routes: dict[str, str]
    cors_hosts: set[str]


DEFAULT_CONFIG: Config = {
    "listen_host": "127.0.0.1",
    "listen_port": 18080,
    "pac_port": 18081,
    "upstream_port": 443,
    "max_workers": 64,
    "connect_timeout": 20,
    "read_timeout": 30,
    "routes": {
        "internal-api-drive-stream.feishu.cn": "drive-stream.feishu.cn",
        "internal-api-lark-api.feishu.cn": "api-lark-api.feishu.cn",
        "weboffice.feishu-3rd-party-services.com": "weboffice.feishuapp.cn",
    },
    "cors_hosts": {"internal-api-lark-api.feishu.cn"},
}


def default_base() -> Path:
    return Path(__file__).resolve().parent / "run"


def _load_routes(data: dict[str, object]) -> dict[str, str]:
    raw = data.get("routes")
    if raw is None:
        return dict(DEFAULT_CONFIG["routes"])
    if not isinstance(raw, dict):
        raise ValueError("config routes must be an object, got %s" % type(raw).__name__)
    invalid = [key for key, value in raw.items()
               if not isinstance(key, str) or not isinstance(value, str)]
    if invalid:
        raise ValueError("config routes must map strings to strings: %s" % invalid)
    return {key: value for key, value in raw.items()
            if isinstance(key, str) and isinstance(value, str)}


def _load_cors_hosts(data: dict[str, object]) -> set[str]:
    raw = data.get("cors_hosts")
    if raw is None:
        return set(DEFAULT_CONFIG["cors_hosts"])
    if not isinstance(raw, list):
        raise ValueError("config cors_hosts must be a list of strings, got %s"
                         % type(raw).__name__)
    invalid = [item for item in raw if not isinstance(item, str)]
    if invalid:
        raise ValueError("config cors_hosts must contain only strings: %s"
                         % invalid)
    return {str(item) for item in raw if isinstance(item, str)}


def load_config(path: str | Path) -> Config:
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("config file %s must contain an object, got %s"
                         % (path, type(data).__name__))
    config: Config = {**DEFAULT_CONFIG}
    for key, value in data.items():
        if key in DEFAULT_CONFIG and key != "routes" and key != "cors_hosts":
            config[key] = value  # type: ignore[assignment]
    config["routes"] = _load_routes(data)
    config["cors_hosts"] = _load_cors_hosts(data)
    return config


def log_event(base: Path, event: str, **fields: object) -> None:
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "proxy.log"
    if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
        rotated = logs / "proxy.log.1"
        if rotated.exists():
            rotated.unlink()
        path.rename(rotated)
    record = {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
              "event": event}
    record.update(fields)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_pac(base: Path, config: Config) -> Path:
    hostnames = sorted(config["routes"])
    proxied = ",\n".join(
        "    %s: true" % json.dumps(host) for host in hostnames
    )
    content = """function FindProxyForURL(url, host) {
  var proxied = {
%s
  };
  if (proxied[host]) {
    return "PROXY %s:%d";
  }
  return "DIRECT";
}
""" % (proxied, config["listen_host"], config["listen_port"])
    pac = base / "feishu_proxy.pac"
    pac.write_text(content, encoding="utf-8")
    return pac


def setup(base: Path, config: Config) -> None:
    base.mkdir(parents=True, exist_ok=True)
    cert_dir = ensure_certs(base, config["routes"])
    pac = write_pac(base, config)
    print("setup ok")
    print("cert_dir=%s" % cert_dir)
    print("pac=%s" % pac)


def build_server_context(config: Config, base: Path) -> ssl.SSLContext:
    cert_dir = ensure_certs(base, config["routes"])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_dir / "leaf.crt"),
                            str(cert_dir / "leaf.key"))
    context.set_alpn_protocols(["http/1.1"])
    return context


def _read_connect_request(conn: socket.socket) -> bytes | None:
    request = b""
    while b"\r\n\r\n" not in request:
        chunk = conn.recv(4096)
        if not chunk:
            return None
        request += chunk
    first_line = request.split(b"\r\n", 1)[0]
    parts = first_line.split()
    if len(parts) < 3 or parts[0].upper() != b"CONNECT":
        conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
        return None
    return parts[1]


def _reject_connect(conn: socket.socket, base: Path, target: str) -> None:
    log_event(base, "REJECT", target=target)
    conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")


def _open_upstream(upstream_host: str, config: Config) -> BufferedSocket:
    ctx = ssl.create_default_context()
    ctx.set_alpn_protocols(["http/1.1"])
    raw = socket.create_connection(
        (upstream_host, config["upstream_port"]),
        timeout=config["connect_timeout"],
    )
    upstream = ctx.wrap_socket(raw, server_hostname=upstream_host)
    upstream.settimeout(config["read_timeout"])
    return BufferedSocket(upstream)


def _wrap_client(conn: socket.socket, server_ctx: ssl.SSLContext,
                 config: Config) -> BufferedSocket:
    client_tls = server_ctx.wrap_socket(conn, server_side=True)
    client_tls.settimeout(config["read_timeout"])
    return BufferedSocket(client_tls)


def _log_request(base: Path, request_line: bytes,
                 headers: list[tuple[bytes, bytes]]) -> None:
    method = request_line.split(b" ", 1)[0].upper()
    host_header = header_value(headers, "Host") or b""
    log_event(base, "REQ",
              method=method.decode("ascii", "replace"),
              target=request_line.decode("utf-8", "replace"),
              host=host_header.decode("utf-8", "replace"),
              headers=safe_headers(headers))


def _log_response(base: Path, response_head: bytes) -> None:
    status_line = response_head.split(b"\r\n", 1)[0].decode("utf-8", "replace")
    log_event(base, "RES", status=status_line)


def _exchange_request(client: BufferedSocket, upstream: BufferedSocket,
                      config: Config, base: Path, host: str) -> None:
    request_line, headers, body = read_request(client)
    _log_request(base, request_line, headers)
    upstream.sock.sendall(rewrite_request(request_line, headers, body))
    response_head, response_headers, status_code = read_response_head(upstream)
    _log_response(base, response_head)
    if host in config["cors_hosts"]:
        origin = header_value(headers, "Origin")
        response_head = add_cors_headers(response_head, origin, headers)
    client.sock.sendall(response_head)
    forward_response_body(upstream, client.sock, request_line.split(b" ", 1)[0],
                          response_headers, status_code)


def _handle_tunnel(conn: socket.socket, config: Config,
                   server_ctx: ssl.SSLContext, base: Path,
                   target: bytes) -> None:
    target_text = target.decode("ascii", "replace")
    host, _, port = target_text.partition(":")
    log_event(base, "CONNECT", target=target_text)
    if host not in config["routes"] or port != "443":
        _reject_connect(conn, base, target_text)
        return
    conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
    client = _wrap_client(conn, server_ctx, config)
    upstream = _open_upstream(config["routes"][host], config)
    _exchange_request(client, upstream, config, base, host)


def handle(conn: socket.socket, config: Config, server_ctx: ssl.SSLContext,
           base: Path) -> None:
    try:
        target = _read_connect_request(conn)
        if target is None:
            return
        _handle_tunnel(conn, config, server_ctx, base, target)
    except (OSError, EOFError, ValueError, RuntimeError) as exc:
        log_event(base, "ERR", kind=type(exc).__name__, detail=str(exc))
    finally:
        try:
            conn.close()
        except OSError as exc:
            log_event(base, "CLOSE", detail=str(exc))


def _serve_loop(server: socket.socket, config: Config,
                server_ctx: ssl.SSLContext, base: Path,
                executor: ThreadPoolExecutor) -> None:
    while True:
        conn, _ = server.accept()
        executor.submit(handle, conn, config, server_ctx, base)


def run_server(base: Path, config: Config) -> None:
    setup(base, config)
    server_ctx = build_server_context(config, base)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((config["listen_host"], config["listen_port"]))
    server.listen(128)
    print("listening on %s:%s" % (config["listen_host"],
                                  config["listen_port"]), flush=True)
    executor = ThreadPoolExecutor(
        max_workers=config["max_workers"],
        thread_name_prefix="feishu-proxy",
    )
    try:
        _serve_loop(server, config, server_ctx, base, executor)
    except KeyboardInterrupt:
        log_event(base, "STOP", reason="keyboard_interrupt")
    finally:
        server.close()
        executor.shutdown(wait=False, cancel_futures=True)
