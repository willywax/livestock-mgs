"""PreToolUse hook: refuse Edit/Write/NotebookEdit on secret or local-data files.

Blocks (exit 2, message on stderr): .env files (but not *.example), *.db, *.log.
Reads JSON from stdin; any parse problem fails open (exit 0) so it never wedges a session.
"""
import json
import os
import sys


def blocked(path: str) -> str | None:
    name = os.path.basename(path.replace("\\", "/")).lower()
    if name.startswith(".env") and not name.endswith(".example"):
        return "environment files hold secrets; edit them by hand outside Claude"
    if name.endswith((".db", ".sqlite", ".sqlite3")):
        return "local database files must not be edited"
    if name.endswith(".log"):
        return "log files are generated; do not edit them"
    return None


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    inp = data.get("tool_input") or {}
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    if not path:
        return 0
    reason = blocked(path)
    if reason:
        sys.stderr.write(f"BLOCKED by .claude/hooks/protect-files.py: {path}: {reason}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
