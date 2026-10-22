#!/opt/hermes/.venv/bin/python
"""Non-interactive Git credential bridge for the profile-owned Bitbucket token."""

import os
import sys


def _saved(name: str) -> str:
    direct = os.environ.get(name, "")
    if direct:
        return direct
    try:
        from hermes_cli.config import get_env_value_prefer_dotenv

        return get_env_value_prefer_dotenv(name) or ""
    except Exception:
        return ""


prompt = " ".join(sys.argv[1:]).lower()
if "username" in prompt:
    print(_saved("BITBUCKET_REPOSITORY_USERNAME") or "x-token-auth")
elif "password" in prompt:
    print(_saved("BITBUCKET_REPOSITORY_TOKEN"))
