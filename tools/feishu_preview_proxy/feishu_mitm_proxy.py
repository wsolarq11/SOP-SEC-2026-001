"""Local HTTPS CONNECT proxy for Feishu internal preview hosts.

This is the CLI entry point. The proxy runtime lives in proxy_core.py so
parsing, forwarding, certificate generation, and the server loop can be tested
without starting a process.

This is TLS interception. Install the generated CA only on machines where that
behavior is explicitly accepted, and remove it with uninstall.ps1 when the
workaround is no longer needed.
"""
import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from proxy_certs import build_ext_file, ensure_certs, openssl
from proxy_core import (
    DEFAULT_CONFIG,
    build_server_context,
    default_base,
    handle,
    load_config,
    log_event,
    run_server,
    setup,
    write_pac,
)
from proxy_http import (
    BufferedSocket,
    add_cors_headers,
    forward_response_body,
    has_header,
    header_value,
    parse_headers,
    read_chunked,
    read_request,
    read_response_head,
    rewrite_request,
    safe_headers,
)

__all__ = [
    "DEFAULT_CONFIG",
    "BufferedSocket",
    "add_cors_headers",
    "build_ext_file",
    "build_server_context",
    "default_base",
    "ensure_certs",
    "forward_response_body",
    "handle",
    "has_header",
    "header_value",
    "load_config",
    "log_event",
    "openssl",
    "parse_headers",
    "read_chunked",
    "read_request",
    "read_response_head",
    "rewrite_request",
    "run_server",
    "safe_headers",
    "setup",
    "write_pac",
]


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Feishu preview HTTPS proxy")
    parser.add_argument("--port", type=int, help="Override listen port")
    parser.add_argument("--base", default=str(default_base()),
                        help="Runtime directory")
    parser.add_argument("--config", default="", help="JSON config path")
    parser.add_argument("--setup", action="store_true",
                        help="Generate certs and PAC")
    parser.add_argument("--write-pac", action="store_true", help="Write PAC only")
    parser.add_argument("--check", action="store_true",
                        help="Generate artifacts and print paths")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
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
