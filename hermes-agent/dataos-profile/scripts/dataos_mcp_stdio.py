#!/usr/bin/env python3
"""Keep the pinned DataOS CLI's non-protocol output off MCP stdout.

The DataOS CLI image currently writes some startup/error log lines to stdout.
MCP stdio reserves stdout for newline-delimited JSON-RPC, so one such line makes
the client close the connection.  This boundary forwards only valid JSON lines
to Hermes and sends all diagnostic text to stderr.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys


COMMAND = ["/usr/local/bin/dataos-ctl", "develop", "assist", "mcp", "run"]


def main() -> int:
    child = subprocess.Popen(
        COMMAND,
        stdin=sys.stdin.buffer,
        stdout=subprocess.PIPE,
        stderr=None,
        bufsize=0,
    )

    def forward_signal(signum: int, _frame: object) -> None:
        if child.poll() is None:
            child.send_signal(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, forward_signal)

    assert child.stdout is not None
    for raw_line in iter(child.stdout.readline, b""):
        line = raw_line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            sys.stderr.buffer.write(b"[dataos-cli] " + raw_line)
            sys.stderr.buffer.flush()
            continue
        sys.stdout.buffer.write(raw_line)
        sys.stdout.buffer.flush()

    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
