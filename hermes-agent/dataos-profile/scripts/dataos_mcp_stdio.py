#!/usr/bin/env python3
"""Keep the pinned DataOS CLI's non-protocol output off MCP stdout.

The DataOS CLI image currently writes some startup/error log lines to stdout.
MCP stdio reserves stdout for newline-delimited JSON-RPC, so one such line makes
the client close the connection.  This boundary forwards only valid JSON lines
to Hermes and sends all diagnostic text to stderr.
"""

from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile


COMMAND = ["/usr/local/bin/dataos-ctl", "develop", "assist", "mcp", "run"]


def ensure_cli_context() -> Path:
    """Create the non-secret DataOS CLI context required by the MCP command.

    DataOS injects the user ID and API key at process runtime.  The CLI still
    refuses to start without its static config/context files, so initialise
    only that non-secret tenant metadata on the persistent Volume.  The API
    key is deliberately never written to a credential file.
    """

    fqdn = os.environ.get("DATAOS_FQDN", "").strip()
    tenant = os.environ.get("DATAOS_TENANT_ID", "").strip()
    if not fqdn or not tenant:
        raise RuntimeError("DATAOS_FQDN and DATAOS_TENANT_ID are required")

    # Prefer an owner-supplied scoped identity when configured in the Keys UI,
    # but keep the DataOS Service run-as projection as a safe fallback.  Do not
    # require the profile config to copy one variable into the other: an empty
    # interpolation would mask the valid projected Service credentials.
    user_id = (
        os.environ.get("DATAOS_USER_ID", "").strip()
        or os.environ.get("DATAOS_LOGIN_USER", "").strip()
        or os.environ.get("DATAOS_OWNER_ID", "").strip()
        or os.environ.get("DATAOS_RUN_AS_USER", "").strip()
    )
    api_key = (
        os.environ.get("DATAOS_USER_API_KEY", "").strip()
        or os.environ.get("DATAOS_RUN_AS_APIKEY", "").strip()
    )
    if not user_id or not api_key:
        raise RuntimeError("DATAOS user ID and API key are required")

    # dataos-ctl requires a credential YAML even when run-as variables are
    # present.  Keep the whole CLI home process-local so the raw key never
    # lands on the persistent Volume.  The directory is removed in main().
    config_dir = Path(tempfile.mkdtemp(prefix="botsky-dataos-cli-"))
    config_dir.chmod(0o700)
    atexit.register(shutil.rmtree, config_dir, ignore_errors=True)
    os.environ["DATAOS_CONFIG_DIRECTORY"] = str(config_dir)
    bootstrap_env = os.environ.copy()
    # The runtime projection variables are for normal authenticated commands.
    # The CLI's init path interprets some of them as an already-initialised
    # session and then skips writing its static files.  Keep only the target
    # directory while creating the non-secret context.
    for name in (
        "DATAOS_FQDN",
        "DATAOS_TENANT_ID",
        "DATAOS_RUN_AS_USER",
        "DATAOS_RUN_AS_APIKEY",
        "DATAOS_USER_ID",
        "DATAOS_USER_API_KEY",
    ):
        bootstrap_env.pop(name, None)

    # The pinned CLI's --setup-config command writes dataos.config.yaml before
    # entering its interactive context wizard.  Supplying a single approval
    # and discarding the expected EOF is the CLI-supported way to seed the
    # static command catalog without copying version-specific internals here.
    if not (config_dir / "dataos.config.yaml").is_file():
        subprocess.run(
            [COMMAND[0], "init", "--setup-config"],
            input=b"Y\n",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=bootstrap_env,
            check=False,
        )

    context_file = config_dir / "dataos.context.yaml"
    tenancy_file = config_dir / "dataos-agent" / ".dataos.tenancy.config.yaml"
    if not context_file.is_file() or not tenancy_file.is_file():
        result = subprocess.run(
            [
                COMMAND[0],
                "init",
                "--flag-init",
                "--context-name",
                "dataos-agent",
                "--fully-qualified-domain-name",
                fqdn,
                "--tenant-identifier",
                tenant,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=bootstrap_env,
            check=False,
        )
        if result.returncode or not context_file.is_file() or not tenancy_file.is_file():
            detail = result.stdout.decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"DataOS CLI context bootstrap failed: {detail}")

    # JSON string literals are valid YAML scalars and safely quote every
    # operator-supplied character.  Write both locations used by this pinned
    # CLI version.  These files live only in the process-local /tmp directory.
    credential = (
        "user:\n"
        f"    id: {json.dumps(user_id)}\n"
        "    token:\n"
        f"        apikey: {json.dumps(api_key)}\n"
        "        access_token: \"\"\n"
        "        refresh_token: \"\"\n"
    )
    for credential_file in (
        config_dir / f".{fqdn}.dataos.cred.config.yaml",
        config_dir / "dataos-agent" / ".dataos.cred.config.yaml",
    ):
        credential_file.parent.mkdir(parents=True, exist_ok=True)
        credential_file.write_text(credential, encoding="utf-8")
        credential_file.chmod(0o600)

    return config_dir


def main() -> int:
    config_dir: Path | None = None
    try:
        config_dir = ensure_cli_context()
    except Exception as exc:
        print(f"[dataos-cli] {exc}", file=sys.stderr)
        if config_dir is not None:
            shutil.rmtree(config_dir, ignore_errors=True)
        return 1

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

    try:
        return child.wait()
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
