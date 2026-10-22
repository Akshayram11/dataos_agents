#!/usr/bin/env python3
"""Idempotently migrate persisted profiles to the reviewed DataOS boundary."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat


DATAPRODUCT_MCP_BLOCK = '''  dataproduct-mcp:
    url: "https://sawaniks-081726.instance.dataos.cloud/dataproduct-mcp/api/v1"
    headers:
      Authorization: "Bearer ${DATAOS_USER_API_KEY}"
    trust: untrusted
    timeout: 180
    connect_timeout: 60
    supports_parallel_tool_calls: false
    tools:
      include:
        - search
        - table_profile
        - get_lineage
        - vulcan_about
        - vulcan_semantic_schema
        - vulcan_quality
        - vulcan_runs
        - vulcan_query_submit
        - vulcan_query_result
      resources: false
      prompts: false

'''


def canonicalize_dataproduct_mcp(text: str) -> str:
    """Replace old/manual data-product connections without retaining tokens."""

    text = text.replace("mcp-dataos-consumption", "mcp-dataproduct-mcp")
    for name in ("dataos-consumption", "dataproduct-mcp"):
        text = re.sub(
            rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|^[A-Za-z][A-Za-z0-9_-]*:\n|\Z)",
            "",
            text,
        )
    marker = "  dataos-docs:\n"
    if marker not in text:
        raise RuntimeError("cannot place dataproduct-mcp without dataos-docs boundary")
    return text.replace(marker, DATAPRODUCT_MCP_BLOCK + marker, 1)


def remove_openai_key(home: Path) -> None:
    """Remove the retired OpenAI credential without logging its value."""
    env_path = home / ".env"
    if not env_path.is_file():
        return
    original = env_path.read_text(encoding="utf-8")
    lines = [
        line for line in original.splitlines(keepends=True)
        if not line.lstrip().startswith("OPENAI_API_KEY=")
    ]
    updated = "".join(lines)
    if updated == original:
        return
    tmp = env_path.with_name(env_path.name + ".dataos-migrate.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.chmod(stat.S_IMODE(env_path.stat().st_mode))
    os.replace(tmp, env_path)
    print("[dataos] removed retired OpenAI credential")


def main() -> None:
    path = Path(os.environ.get("HERMES_HOME", "/opt/data")) / "config.yaml"
    if not path.is_file():
        return

    original = path.read_text(encoding="utf-8")
    updated = original.replace(
        'DATAOS_RUN_AS_USER: "${DATAOS_RUN_AS_USER}"',
        'DATAOS_RUN_AS_USER: "${DATAOS_USER_ID}"',
    ).replace(
        'DATAOS_RUN_AS_APIKEY: "${DATAOS_RUN_AS_APIKEY}"',
        'DATAOS_RUN_AS_APIKEY: "${DATAOS_USER_API_KEY}"',
    ).replace(
        'Authorization: "Bearer ${DATAOS_RUN_AS_APIKEY}"',
        'Authorization: "Bearer ${DATAOS_USER_API_KEY}"',
    )
    updated = canonicalize_dataproduct_mcp(updated)

    # MCP subprocesses receive only their declared env block. Pass both the
    # optional owner credentials and the Service projections; the wrapper
    # chooses owner values when present and otherwise uses the run-as pair.
    env_block = (
        '    env:\n'
        '      DATAOS_USER_ID: "${DATAOS_USER_ID}"\n'
        '      DATAOS_USER_API_KEY: "${DATAOS_USER_API_KEY}"\n'
        '      DATAOS_LOGIN_USER: "${HERMES_DASHBOARD_BASIC_AUTH_USERNAME}"\n'
        '      DATAOS_OWNER_ID: "${DATAOS_OWNER_ID}"\n'
        '      DATAOS_RUN_AS_USER: "${DATAOS_RUN_AS_USER}"\n'
        '      DATAOS_RUN_AS_APIKEY: "${DATAOS_RUN_AS_APIKEY}"\n'
        '      DATAOS_FQDN: "${DATAOS_FQDN}"\n'
        '      DATAOS_TENANT_ID: "${DATAOS_TENANT_ID}"\n'
        '      LOG_LEVEL: "error"'
    )

    updated = updated.replace(
        "    command: dataos-ctl\n    args: [develop, assist, mcp, run]",
        "    command: /opt/hermes/.venv/bin/python\n"
        "    args: [/opt/hermes/dataos-profile/scripts/dataos_mcp_stdio.py]",
        1,
    )

    args_line = "    args: [/opt/hermes/dataos-profile/scripts/dataos_mcp_stdio.py]"
    if args_line in updated:
        start = updated.find("    env:\n", updated.find(args_line) + len(args_line))
        end = updated.find("    trust:", start)
        if start != -1 and end != -1:
            updated = updated[:start] + env_block + "\n" + updated[end:]

    if "\nplatforms:\n" not in updated:
        updated = updated.rstrip() + "\n\nplatforms:\n  api_server:\n    enabled: false\n"

    if "\ndisplay:\n" not in updated and "\ndisplay:" not in updated:
        updated = updated.rstrip() + "\n\ndisplay:\n  skin: botsky\n"
    elif "skin:" not in updated.split("\ndisplay:", 1)[-1].split("\n\n", 1)[0]:
        # Existing display block without a skin — pin Botsky branding.
        updated = updated.replace("\ndisplay:\n", "\ndisplay:\n  skin: botsky\n", 1)

    home = path.parent
    remove_openai_key(home)

    # This distribution uses a Claude Code OAuth setup-token, not an OpenAI
    # API key. Migrate the persisted model selection on existing Volumes.
    updated = re.sub(
        r"(?m)^(\s*provider:)\s*openai\s*$",
        r"\1 anthropic",
        updated,
        count=1,
    )
    updated = re.sub(
        r"(?m)^(\s*default:)\s*(?:openai/)?gpt-5\.6-luna\s*$",
        r"\1 claude-sonnet-4-6",
        updated,
        count=1,
    )
    skin_src = Path("/opt/hermes/dataos-profile/skins/botsky.yaml")
    skin_dest = home / "skins" / "botsky.yaml"
    if skin_src.is_file() and not skin_dest.exists():
        skin_dest.parent.mkdir(parents=True, exist_ok=True)
        skin_dest.write_text(skin_src.read_text(encoding="utf-8"), encoding="utf-8")
        print("[dataos] seeded botsky skin into persisted profile")

    if updated == original:
        print("[dataos] persisted profile already current")
        return

    tmp = path.with_name(path.name + ".dataos-migrate.tmp")
    tmp.write_text(updated, encoding="utf-8")
    tmp.chmod(stat.S_IMODE(path.stat().st_mode))
    os.replace(tmp, path)
    print("[dataos] migrated persisted profile credential and platform boundaries")


if __name__ == "__main__":
    main()
