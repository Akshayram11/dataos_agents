#!/opt/hermes/.venv/bin/python
"""Non-interactive Git credential bridge for profile-owned repository tokens.

The historical filename is retained because deployed profiles already point
``GIT_ASKPASS`` at it. Credentials are selected from the Git prompt hostname;
tokens never appear in a remote URL, command argument, or Git configuration.
"""

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
provider = "github" if "github.com" in prompt else "bitbucket" if "bitbucket.org" in prompt else (_saved("REPOSITORY_PROVIDER") or "bitbucket").lower()
if provider == "github":
    username = _saved("GITHUB_REPOSITORY_USERNAME") or "x-access-token"
    token = _saved("GITHUB_REPOSITORY_TOKEN")
else:
    username = _saved("BITBUCKET_REPOSITORY_USERNAME") or "x-token-auth"
    token = _saved("BITBUCKET_REPOSITORY_TOKEN")

if "username" in prompt:
    print(_saved("REPOSITORY_USERNAME") or username)
elif "password" in prompt:
    print(_saved("REPOSITORY_TOKEN") or token)
