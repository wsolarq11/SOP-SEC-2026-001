"""HTTP CONNECT request/response helpers for the Feishu preview proxy.

Only byte-level HTTP parsing and forwarding live here so the proxy runtime
stays independent from certificate generation.
"""
from __future__ import annotations

import socket

CHUNK_SIZE = 65536


def safe_headers(headers: list[tuple[bytes, bytes]]) -> str:
    safe = []
    for name, value in headers:
        lowered = name.lower()
        if lowered in (b"cookie", b"authorization", b"proxy-authorization"):
            continue
        safe.append("%s=%s" % (
            name.decode("utf-8", "replace"),
            value.decode("utf-8", "replace"),
        ))
    return "; ".join(safe)


class BufferedSocket:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.buf = b""

    def recv_until(self, marker: bytes) -> bytes:
        while marker not in self.buf:
            chunk = self.sock.recv(CHUNK_SIZE)
            if not chunk:
                raise EOFError("connection closed")
            self.buf += chunk
        index = self.buf.index(marker) + len(marker)
        out = self.buf[:index]
        self.buf = self.buf[index:]
        return out

    def recv_exact(self, size: int) -> bytes:
        while len(self.buf) < size:
            chunk = self.sock.recv(CHUNK_SIZE)
            if not chunk:
                raise EOFError("connection closed")
            self.buf += chunk
        out = self.buf[:size]
        self.buf = self.buf[size:]
        return out


def parse_headers(header_block: bytes) -> list[tuple[bytes, bytes]]:
    headers = []
    for line in header_block.split(b"\r\n")[1:]:
        if not line:
            continue
        name, _, value = line.partition(b":")
        headers.append((name.strip(), value.strip()))
    return headers


def header_value(headers: list[tuple[bytes, bytes]], name: str) -> bytes | None:
    lowered = name.lower().encode("ascii")
    for key, value in headers:
        if key.lower() == lowered:
            return value
    return None


def has_header(headers: list[tuple[bytes, bytes]], name: str) -> bool:
    return header_value(headers, name) is not None


def _filter_response_headers(lines: list[bytes]) -> list[bytes]:
    skip = {
        b"access-control-allow-origin",
        b"access-control-allow-credentials",
        b"access-control-allow-methods",
        b"access-control-allow-headers",
        b"access-control-expose-headers",
        b"access-control-max-age",
    }
    kept = []
    for line in lines[1:]:
        if line == b"":
            continue
        name, _, _ = line.partition(b":")
        if name.strip().lower() not in skip:
            kept.append(line)
    return kept


def _allowed_headers_line(request_headers: list[tuple[bytes, bytes]]) -> bytes:
    requested = header_value(request_headers, "Access-Control-Request-Headers")
    if requested:
        return b"Access-Control-Allow-Headers: " + requested
    return (
        b"Access-Control-Allow-Headers: Content-Type, Authorization, X-Request-Id, "
        b"X-TT-Logid, X-Lark-Request-Id, X-Requested-With, X-CSRF-Token, X-B3-Traceid"
    )


def _cors_lines(origin: bytes | None,
                request_headers: list[tuple[bytes, bytes]]) -> list[bytes]:
    cors = []
    if origin:
        cors.append(b"Access-Control-Allow-Origin: " + origin)
        cors.append(b"Access-Control-Allow-Credentials: true")
    cors.append(
        b"Access-Control-Allow-Methods: GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS"
    )
    cors.append(_allowed_headers_line(request_headers))
    cors.append(
        b"Access-Control-Expose-Headers: Content-Disposition, X-Request-Id, X-TT-Logid, "
        b"X-Lark-Request-Id, X-CSRF-Token"
    )
    cors.append(b"Access-Control-Max-Age: 86400")
    return cors


def add_cors_headers(response_head: bytes, origin: bytes | None,
                     request_headers: list[tuple[bytes, bytes]]) -> bytes:
    lines = response_head.split(b"\r\n")
    if not lines:
        return response_head
    kept = _filter_response_headers(lines)
    return b"\r\n".join([lines[0]] + _cors_lines(origin, request_headers)
                        + kept) + b"\r\n\r\n"


def read_request(
    client: BufferedSocket,
) -> tuple[bytes, list[tuple[bytes, bytes]], bytes]:
    head = client.recv_until(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    request_line = lines[0]
    headers = parse_headers(head)
    method = request_line.split(b" ", 1)[0].upper()
    body = b""
    if method in (b"POST", b"PUT", b"PATCH"):
        if has_header(headers, "Transfer-Encoding"):
            body = read_chunked(client)
        else:
            length = int(header_value(headers, "Content-Length") or b"0")
            body = client.recv_exact(length)
    return request_line, headers, body


def _read_chunk_trailers(client: BufferedSocket) -> bytes:
    body = b""
    while True:
        trailer_line = client.recv_until(b"\r\n")[:-2]
        body += trailer_line + b"\r\n"
        if trailer_line == b"":
            return body


def read_chunked(client: BufferedSocket) -> bytes:
    body = b""
    while True:
        size_line = client.recv_until(b"\r\n")[:-2]
        size = int(size_line.split(b";", 1)[0], 16)
        body += size_line + b"\r\n"
        if size == 0:
            return body + _read_chunk_trailers(client)
        body += client.recv_exact(size)
        body += client.recv_exact(2)


def rewrite_request(request_line: bytes,
                    headers: list[tuple[bytes, bytes]],
                    body: bytes) -> bytes:
    new_headers = [
        item for item in headers
        if item[0].lower() != b"proxy-connection"
    ]
    if not has_header(new_headers, "Connection"):
        new_headers.append((b"Connection", b"keep-alive"))
    lines = [request_line]
    for name, value in new_headers:
        lines.append(name + b": " + value)
    return b"\r\n".join(lines) + b"\r\n\r\n" + body


def read_response_head(
    upstream: BufferedSocket,
) -> tuple[bytes, list[tuple[bytes, bytes]], int]:
    head = upstream.recv_until(b"\r\n\r\n")
    headers = parse_headers(head)
    status_line = head.split(b"\r\n", 1)[0]
    status_code = int(status_line.split(b" ", 2)[1])
    return head, headers, status_code


def _forward_chunk_trailers(upstream: BufferedSocket,
                            client: socket.socket) -> None:
    while True:
        trailer = upstream.recv_until(b"\r\n")
        client.sendall(trailer)
        if trailer == b"\r\n":
            return


def _forward_chunked(upstream: BufferedSocket, client: socket.socket) -> None:
    while True:
        size_line = upstream.recv_until(b"\r\n")
        client.sendall(size_line)
        size = int(size_line[:-2].split(b";", 1)[0], 16)
        if size == 0:
            _forward_chunk_trailers(upstream, client)
            return
        body = upstream.recv_exact(size)
        client.sendall(body)
        client.sendall(upstream.recv_exact(2))


def _forward_fixed(upstream: BufferedSocket, client: socket.socket,
                   remaining: int) -> None:
    while remaining > 0:
        chunk = upstream.sock.recv(min(CHUNK_SIZE, remaining))
        if not chunk:
            raise EOFError("connection closed during response body")
        client.sendall(chunk)
        remaining -= len(chunk)


def _forward_until_eof(upstream: BufferedSocket, client: socket.socket) -> None:
    while True:
        chunk = upstream.sock.recv(CHUNK_SIZE)
        if not chunk:
            return
        client.sendall(chunk)


def forward_response_body(upstream: BufferedSocket, client: socket.socket,
                          method: bytes, headers: list[tuple[bytes, bytes]],
                          status_code: int) -> None:
    if method == b"HEAD" or status_code in (204, 304) or 100 <= status_code < 200:
        return
    if has_header(headers, "Transfer-Encoding"):
        _forward_chunked(upstream, client)
        return
    length_value = header_value(headers, "Content-Length")
    if length_value is not None:
        _forward_fixed(upstream, client, int(length_value))
        return
    _forward_until_eof(upstream, client)
