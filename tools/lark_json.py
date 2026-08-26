"""Parse lark-cli JSON output for publish/backup scripts.

The shell scripts must not use grep/sed to read machine output. This helper
keeps the JSON contract in one tested place:
  lark_json.py ok       -> exit 0 only when data.ok is true
  lark_json.py token    -> print file_token when upload succeeded
  lark_json.py message  -> print the human-readable error field if present
"""
import json
import sys
from collections.abc import Sequence

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\n")


def parse_json(text: str) -> dict[str, object]:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    data = json.loads(text[start:])
    if not isinstance(data, dict):
        raise ValueError("lark JSON output must be an object, got %s"
                         % type(data).__name__)
    return data


def is_ok(data: dict[str, object]) -> bool:
    value = data.get("ok")
    return value is True or str(value).lower() == "true"


def file_token(data: dict[str, object]) -> str | None:
    token = data.get("file_token")
    if isinstance(token, str):
        return token
    nested = data.get("data")
    if isinstance(nested, dict):
        value = nested.get("file_token")
        return value if isinstance(value, str) else None
    return None


def message_text(data: dict[str, object]) -> str:
    for source in (data, data.get("data") if isinstance(data.get("data"), dict) else {}):
        msg = source.get("message")
        if msg:
            if isinstance(msg, str):
                return msg
            return json.dumps(msg, ensure_ascii=False)
    return ""


def _run_field(field: str, data: dict[str, object]) -> int:
    if field == "ok":
        return 0 if is_ok(data) else 1
    if field == "token":
        token = file_token(data)
        if is_ok(data) and token:
            print(token)
            return 0
        return 1
    if field == "message":
        msg = message_text(data)
        if msg:
            print(msg)
        return 0
    print("unknown field: %s" % field, file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: lark_json.py ok|token|message", file=sys.stderr)
        return 2
    field = args[0]
    try:
        data = parse_json(sys.stdin.read())
    except Exception as exc:
        if field in ("ok", "token"):
            return 1
        print("cannot parse lark-cli output: %s" % exc, file=sys.stderr)
        return 1
    return _run_field(field, data)


if __name__ == "__main__":
    sys.exit(main())
