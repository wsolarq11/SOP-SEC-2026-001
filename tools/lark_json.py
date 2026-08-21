"""Parse lark-cli JSON output for publish/backup scripts.

The shell scripts must not use grep/sed to read machine output. This helper
keeps the JSON contract in one tested place:
  lark_json.py ok       -> exit 0 only when data.ok is true
  lark_json.py token    -> print file_token when upload succeeded
  lark_json.py message  -> print the human-readable error field if present
"""
import json
import sys


def parse_json(text):
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[start:])


def is_ok(data):
    value = data.get("ok")
    return value is True or str(value).lower() == "true"


def message_text(data):
    msg = data.get("message")
    if isinstance(msg, str):
        return msg
    if msg is not None:
        return json.dumps(msg, ensure_ascii=False)
    return ""


def main():
    if len(sys.argv) != 2:
        print("usage: lark_json.py ok|token|message", file=sys.stderr)
        return 2
    field = sys.argv[1]
    try:
        data = parse_json(sys.stdin.read())
    except Exception as exc:
        if field in ("ok", "token"):
            return 1
        print("cannot parse lark-cli output: %s" % exc, file=sys.stderr)
        return 1
    if field == "ok":
        return 0 if is_ok(data) else 1
    if field == "token":
        token = data.get("file_token")
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


if __name__ == "__main__":
    sys.exit(main())
