"""Certificate generation for the local HTTPS interception proxy.

The CA is kept stable across runs; the leaf certificate is rebuilt whenever the
routed hostname set changes so browsers trust the SAN actually presented by the
proxy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def openssl(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
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


def build_ext_file(hostnames: list[str]) -> str:
    san = ", ".join("DNS:%s" % host for host in sorted(hostnames))
    return "\n".join([
        "basicConstraints = critical, CA:FALSE",
        "keyUsage = critical, digitalSignature, keyEncipherment",
        "extendedKeyUsage = serverAuth",
        "subjectAltName = %s" % san,
        "",
    ])


def _ext_matches(base: Path, routes: dict[str, str]) -> bool:
    ext_file = base / "certs" / "ext.cnf"
    if not ext_file.is_file():
        return False
    return ext_file.read_text(encoding="utf-8") == build_ext_file(list(routes))


def _remove_leaf_artifacts(cert_dir: Path) -> None:
    for name in ("leaf.crt", "leaf.key", "leaf.csr"):
        path = cert_dir / name
        if path.exists():
            path.unlink()


def _cert_paths(base: Path) -> tuple[Path, Path, Path, Path, Path]:
    cert_dir = base / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    return (cert_dir, cert_dir / "ca.crt", cert_dir / "ca.key",
            cert_dir / "leaf.crt", cert_dir / "leaf.key")


def _generate_ca(cert_dir: Path, ca_crt: Path, ca_key: Path) -> None:
    openssl([
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(ca_key), "-out", str(ca_crt), "-days", "3650",
        "-subj", "/CN=Local Feishu Preview Proxy CA",
    ], cert_dir)


def _generate_leaf(cert_dir: Path, routes: dict[str, str]) -> None:
    ext_file = cert_dir / "ext.cnf"
    ext_file.write_text(build_ext_file(list(routes)), encoding="utf-8")
    openssl([
        "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(cert_dir / "leaf.key"), "-out", str(cert_dir / "leaf.csr"),
        "-subj", "/CN=Local Feishu Preview Proxy Leaf",
    ], cert_dir)
    openssl([
        "x509", "-req", "-in", str(cert_dir / "leaf.csr"),
        "-CA", str(cert_dir / "ca.crt"), "-CAkey", str(cert_dir / "ca.key"),
        "-set_serial", "0x46455348", "-days", "825", "-sha256",
        "-extfile", str(ext_file), "-out", str(cert_dir / "leaf.crt"),
    ], cert_dir)


def ensure_certs(base: Path, routes: dict[str, str]) -> Path:
    cert_dir, ca_crt, ca_key, leaf_crt, leaf_key = _cert_paths(base)
    if leaf_crt.exists() and leaf_key.exists() and ca_crt.exists() and ca_key.exists():
        if _ext_matches(base, routes):
            return cert_dir
        _remove_leaf_artifacts(cert_dir)
    if not ca_crt.exists() or not ca_key.exists():
        _generate_ca(cert_dir, ca_crt, ca_key)
    _generate_leaf(cert_dir, routes)
    return cert_dir
