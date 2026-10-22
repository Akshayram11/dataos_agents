#!/usr/bin/env python3
"""Idempotently migrate persisted profiles to the reviewed DataOS boundary."""

from __future__ import annotations

import os
from pathlib import Path
import stat


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

    updated = updated.replace(
        "    command: dataos-ctl\n    args: [develop, assist, mcp, run]",
        "    command: /opt/hermes/.venv/bin/python\n"
        "    args: [/opt/hermes/dataos-profile/scripts/dataos_mcp_stdio.py]",
        1,
    )

    tenant_line = '      DATAOS_TENANT_ID: "${DATAOS_TENANT_ID}"'
    if '      LOG_LEVEL: "error"' not in updated and tenant_line in updated:
        updated = updated.replace(tenant_line, tenant_line + '\n      LOG_LEVEL: "error"', 1)

    if "\nplatforms:\n" not in updated:
        updated = updated.rstrip() + "\n\nplatforms:\n  api_server:\n    enabled: false\n"

    if "\ndisplay:\n" not in updated and "\ndisplay:" not in updated:
        updated = updated.rstrip() + "\n\ndisplay:\n  skin: botsky\n"
    elif "skin:" not in updated.split("\ndisplay:", 1)[-1].split("\n\n", 1)[0]:
        # Existing display block without a skin — pin Botsky branding.
        updated = updated.replace("\ndisplay:\n", "\ndisplay:\n  skin: botsky\n", 1)

    home = path.parent
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
