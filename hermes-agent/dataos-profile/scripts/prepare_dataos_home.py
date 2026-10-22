#!/usr/bin/env python3
"""Prepare a user-owned Hermes home on a root-owned DataOS disk mount.

DataOS mounts the persistent disk at ``/opt/data`` as root:1000.  The
workload's uid 1000 can create children there, but Hermes deliberately refuses
to use the root-owned mount point itself as its control directory.  Keep the
mount root as infrastructure and use ``/opt/data/hermes`` as application state.
"""

from __future__ import annotations

import os
from pathlib import Path


MARKER = ".dataos-home-v1"
IGNORED = {"lost+found"}


def _inside(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return child != parent


def main() -> None:
    volume = Path(os.environ.get("HERMES_DATAOS_VOLUME_ROOT", "/opt/data"))
    home = Path(os.environ.get("HERMES_HOME", "/opt/data/hermes"))

    volume = volume.absolute()
    home = home.absolute()
    if not _inside(volume, home):
        raise SystemExit(f"refusing DataOS home outside {volume}")
    if volume.is_symlink() or home.is_symlink():
        raise SystemExit("refusing symlinked DataOS volume or Hermes home")

    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    home.chmod(0o700)
    marker = home / MARKER
    if marker.exists():
        print(f"[dataos] application home ready: {home}")
        return

    conflicts: list[str] = []
    moved = 0
    for source in sorted(volume.iterdir(), key=lambda path: path.name):
        if source == home or source.name in IGNORED:
            continue
        destination = home / source.name
        if destination.exists() or destination.is_symlink():
            conflicts.append(source.name)
            continue
        os.replace(source, destination)
        moved += 1

    if conflicts:
        names = ", ".join(conflicts)
        raise SystemExit(f"DataOS home migration stopped; destination conflicts: {names}")

    marker.write_text("DataOS application state lives in this directory.\n", encoding="utf-8")
    marker.chmod(0o600)
    print(f"[dataos] application home ready: {home} ({moved} legacy entries migrated)")


if __name__ == "__main__":
    main()
