"""Local HTTPS CONNECT proxy for Feishu internal preview hosts.

This tool is a narrow local workaround for one class of failure: Feishu's
preview iframe requests internal hostnames that are not reachable from the
current machine. A PAC file routes only those hostnames to this proxy, and the
proxy connects to reachable public aliases while preserving the original Host
header.

This is TLS interception. Install the generated CA only on machines where that
behavior is explicitly accepted, and remove it with uninstall.ps1 when the
workaround is no longer needed.
"""

import argparse
import json
import socket
import ssl
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

DEFAULT_CONFIG = {
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
}

MAX_LOG_BYTES = 5 * 1024 * 1024
CHUNK_SIZE = 65536


def default_base():
    return Path(__file__).resolve().parent / "run"


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    config = dict(DEFAULT_CONFIG)
    config.update(data)
    routes = data.get("routes")
    if routes:
        config["routes"] = dict(routes)
    return config


def log(base, message):
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "proxy.log"
    if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
        rotated = logs / "proxy.log.1"
        if rotated.exists():
            rotated.unlink()
        path.rename(rotated)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (timestamp, message))


def safe_headers(headers):
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
    def __init__(self, sock):
        self.sock = sock
        self.buf = b""

    def recv_until(self, marker):
        while marker not in self.buf:
            chunk = self.sock.recv(CHUNK_SIZE)
            if not chunk:
                raise EOFError("connection closed")
            self.buf += chunk
        index = self.buf.index(marker) + len(marker)
        out = self.buf[:index]
        self.buf = self.buf[index:]
        return out

    def recv_exact(self, size):
        while len(self.buf) < size:
            chunk = self.sock.recv(CHUNK_SIZE)
            if not chunk:
                raise EOFError("connection closed")
            self.buf += chunk
        out = self.buf[:size]
        self.buf = self.buf[size:]
        return out


def parse_headers(header_block):
    lines = header_block.split(b"\r\n")
    headers = []
    for line in lines[1:]:
        if not line:
            continue
        name, _, value = line.partition(b":")
        headers.append((name.strip(), value.strip()))
    return headers


def header_value(headers, name):
    lowered = name.lower().encode("ascii")
    for key, value in headers:
        if key.lower() == lowered:
            return value
    return None


def has_header(headers, name):
    return header_value(headers, name) is not None


def add_cors_headers(response_head, origin, request_headers):
    lines = response_head.split(b"\r\n")
    if not lines:
        return response_head
    status_line = lines[0]
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
    cors = []
    if origin:
        cors.append(b"Access-Control-Allow-Origin: " + origin)
        cors.append(b"Access-Control-Allow-Credentials: true")
    cors.append(b"Access-Control-Allow-Methods: GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS")
    requested_headers = header_value(request_headers, "Access-Control-Request-Headers")
    if requested_headers:
        cors.append(b"Access-Control-Allow-Headers: " + requested_headers)
    else:
        cors.append(b"Access-Control-Allow-Headers: Content-Type, Authorization, X-Request-Id, X-TT-Logid, X-Lark-Request-Id, X-Requested-With, X-CSRF-Token, X-B3-Traceid")
    cors.append(b"Access-Control-Expose-Headers: Content-Disposition, X-Request-Id, X-TT-Logid, X-Lark-Request-Id, X-CSRF-Token")
    cors.append(b"Access-Control-Max-Age: 86400")
    return b"\r\n".join([status_line] + cors + kept) + b"\r\n\r\n"


def read_request(client):
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


def read_chunked(client):
    body = b""
    while True:
        size_line = client.recv_until(b"\r\n")[:-2]
        size = int(size_line.split(b";", 1)[0], 16)
        body += size_line + b"\r\n"
        if size == 0:
            while True:
                trailer_line = client.recv_until(b"\r\n")[:-2]
                body += trailer_line + b"\r\n"
                if trailer_line == b"":
                    return body
        body += client.recv_exact(size)
        body += client.recv_exact(2)


def rewrite_request(request_line, headers, body):
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


def read_response_head(upstream):
    head = upstream.recv_until(b"\r\n\r\n")
    headers = parse_headers(head)
    status_line = head.split(b"\r\n", 1)[0]
    status_code = int(status_line.split(b" ", 2)[1])
    return head, headers, status_code


def forward_response_body(upstream, client, method, headers, status_code):
    if method == b"HEAD" or status_code in (204, 304) or 100 <= status_code < 200:
        return
    if has_header(headers, "Transfer-Encoding"):
        while True:
            size_line = upstream.recv_until(b"\r\n")
            client.sendall(size_line)
            size = int(size_line[:-2].split(b";", 1)[0], 16)
            if size == 0:
                while True:
                    trailer = upstream.recv_until(b"\r\n")
                    client.sendall(trailer)
                    if trailer == b"\r\n":
                        return
            body = upstream.recv_exact(size)
            client.sendall(body)
            client.sendall(upstream.recv_exact(2))
        return
    length_value = header_value(headers, "Content-Length")
    if length_value is not None:
        remaining = int(length_value)
        while remaining > 0:
            chunk = upstream.sock.recv(min(CHUNK_SIZE, remaining))
            if not chunk:
                raise EOFError("connection closed during response body")
            client.sendall(chunk)
            remaining -= len(chunk)
        return
    while True:
        chunk = upstream.sock.recv(CHUNK_SIZE)
        if not chunk:
            return
        client.sendall(chunk)


def openssl(args, cwd):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        ["openssl"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[-500:]
        raise RuntimeError("openssl failed: %s" % detail)
    return proc


def build_ext_file(hostnames):
    san = ", ".join("DNS:%s" % host for host in sorted(hostnames))
    return "\n".join([
        "basicConstraints = critical, CA:FALSE",
        "keyUsage = critical, digitalSignature, keyEncipherment",
        "extendedKeyUsage = serverAuth",
        "subjectAltName = %s" % san,
        "",
    ])


def ensure_certs(base, routes):
    cert_dir = base / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_crt = cert_dir / "ca.crt"
    ca_key = cert_dir / "ca.key"
    leaf_crt = cert_dir / "leaf.crt"
    leaf_key = cert_dir / "leaf.key"

    if leaf_crt.exists() and leaf_key.exists() and ca_crt.exists() and ca_key.exists():
        return cert_dir

    if not ca_crt.exists() or not ca_key.exists():
        openssl([
            "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(ca_key), "-out", str(ca_crt), "-days", "3650",
            "-subj", "/CN=Local Feishu Preview Proxy CA",
        ], cert_dir)

    leaf_csr = cert_dir / "leaf.csr"
    ext_file = cert_dir / "ext.cnf"
    ext_file.write_text(build_ext_file(routes), encoding="utf-8")
    openssl([
        "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(leaf_key), "-out", str(leaf_csr),
        "-subj", "/CN=Local Feishu Preview Proxy Leaf",
    ], cert_dir)
    openssl([
        "x509", "-req", "-in", str(leaf_csr),
        "-CA", str(ca_crt), "-CAkey", str(ca_key),
        "-set_serial", "0x46455348", "-days", "825", "-sha256",
        "-extfile", str(ext_file), "-out", str(leaf_crt),
    ], cert_dir)
    return cert_dir


def write_pac(base, config):
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


def setup(base, config):
    base.mkdir(parents=True, exist_ok=True)
    cert_dir = ensure_certs(base, config["routes"])
    pac = write_pac(base, config)
    print("setup ok")
    print("cert_dir=%s" % cert_dir)
    print("pac=%s" % pac)


def build_server_context(config, base):
    cert_dir = ensure_certs(base, config["routes"])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_dir / "leaf.crt"), str(cert_dir / "leaf.key"))
    context.set_alpn_protocols(["http/1.1"])
    return context


def handle(conn, config, server_ctx, base):
    try:
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = conn.recv(4096)
            if not chunk:
                return
            request += chunk
        first_line = request.split(b"\r\n", 1)[0]
        parts = first_line.split()
        if len(parts) < 3 or parts[0].upper() != b"CONNECT":
            conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        target = parts[1].decode("ascii", "replace")
        host, _, port = target.partition(":")
        log(base, "CONNECT %s" % target)
        if host not in config["routes"] or port != "443":
            log(base, "REJECT %s" % target)
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            return
        upstream_host = config["routes"][host]

        conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")

        client_tls = server_ctx.wrap_socket(conn, server_side=True)
        client_tls.settimeout(config["read_timeout"])
        client = BufferedSocket(client_tls)

        request_line, headers, body = read_request(client)
        method = request_line.split(b" ", 1)[0].upper()
        host_header = header_value(headers, "Host") or b""
        log(base, "REQ %s %s host=%s" % (
            method.decode("ascii", "replace"),
            request_line.decode("utf-8", "replace"),
            host_header.decode("utf-8", "replace"),
        ))
        log(base, "HEAD %s" % safe_headers(headers))

        upstream_ctx = ssl.create_default_context()
        upstream_ctx.set_alpn_protocols(["http/1.1"])
        upstream_raw = socket.create_connection(
            (upstream_host, config["upstream_port"]),
            timeout=config["connect_timeout"],
        )
        upstream = upstream_ctx.wrap_socket(upstream_raw, server_hostname=upstream_host)
        upstream.settimeout(config["read_timeout"])
        up = BufferedSocket(upstream)
        upstream.sendall(rewrite_request(request_line, headers, body))

        response_head, response_headers, status_code = read_response_head(up)
        status_line = response_head.split(b"\r\n", 1)[0].decode("utf-8", "replace")
        log(base, "RES %s" % status_line)
        if host == "internal-api-lark-api.feishu.cn":
            origin = header_value(headers, "Origin")
            response_head = add_cors_headers(response_head, origin, headers)
        client_tls.sendall(response_head)
        forward_response_body(up, client_tls, method, response_headers, status_code)
    except (OSError, EOFError, ValueError, RuntimeError) as exc:
        log(base, "ERR %s: %s" % (type(exc).__name__, exc))
    finally:
        try:
            conn.close()
        except OSError:
            pass


def run_server(base, config):
    setup(base, config)
    server_ctx = build_server_context(config, base)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((config["listen_host"], config["listen_port"]))
    server.listen(128)
    print("listening on %s:%s" % (config["listen_host"], config["listen_port"]), flush=True)
    executor = ThreadPoolExecutor(
        max_workers=config["max_workers"],
        thread_name_prefix="feishu-proxy",
    )
    try:
        while True:
            conn, _ = server.accept()
            executor.submit(handle, conn, config, server_ctx, base)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        executor.shutdown(wait=False, cancel_futures=True)


def main():
    parser = argparse.ArgumentParser(description="Local Feishu preview HTTPS proxy")
    parser.add_argument("--port", type=int, help="Override listen port")
    parser.add_argument("--base", default=str(default_base()), help="Runtime directory")
    parser.add_argument("--config", default="", help="JSON config path")
    parser.add_argument("--setup", action="store_true", help="Generate certs and PAC")
    parser.add_argument("--write-pac", action="store_true", help="Write PAC only")
    parser.add_argument("--check", action="store_true", help="Generate artifacts and print paths")
    args = parser.parse_args()

    base = Path(args.base)
    config = DEFAULT_CONFIG
    if args.config:
        config = load_config(args.config)
    if args.port:
        config["listen_port"] = args.port

    if args.setup or args.write_pac or args.check:
        setup(base, config)
        return
    run_server(base, config)


if __name__ == "__main__":
    main()
