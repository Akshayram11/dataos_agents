"""Private Git repository workspace management for the DataOS distribution.

Credentials live in the selected Hermes profile's owner-only ``.env``.  The
metadata file deliberately contains only the repository URL, branch and local
path; neither API responses nor git remotes contain the token.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hermes_constants import get_hermes_home
from hermes_cli.web_routers._common import config_scoped_to_thread


router = APIRouter()
Provider = Literal["bitbucket", "github"]
PROVIDER_ENV = "REPOSITORY_PROVIDER"
TOKEN_ENVS = {
    "bitbucket": "BITBUCKET_REPOSITORY_TOKEN",
    "github": "GITHUB_REPOSITORY_TOKEN",
}
USERNAME_ENVS = {
    "bitbucket": "BITBUCKET_REPOSITORY_USERNAME",
    "github": "GITHUB_REPOSITORY_USERNAME",
}
DEFAULT_USERNAMES = {"bitbucket": "x-token-auth", "github": "x-access-token"}
HOSTS = {"bitbucket": "bitbucket.org", "github": "github.com"}
METADATA_NAME = "repository-workspace.json"
LEGACY_METADATA_NAME = "bitbucket-workspace.json"
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")


class RepositoryWorkspacePut(BaseModel):
    provider: Provider
    repository_url: str = Field(min_length=1, max_length=500)
    branch: str = Field(default="main", min_length=1, max_length=200)
    token: str = Field(default="", max_length=4096)
    username: str = Field(default="x-token-auth", max_length=200)
    commit_name: str = Field(default="", max_length=200)
    commit_email: str = Field(default="", max_length=320)
    prepare_workspace: bool = True


def _metadata_path() -> Path:
    return get_hermes_home() / "workspace" / METADATA_NAME


def _legacy_metadata_path() -> Path:
    return get_hermes_home() / "workspace" / LEGACY_METADATA_NAME


def _repos_root() -> Path:
    return get_hermes_home() / "workspace" / "repos"


def _read_metadata() -> dict:
    path = _metadata_path()
    if not path.is_file():
        path = _legacy_metadata_path()
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_metadata(value: dict) -> None:
    path = _metadata_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{METADATA_NAME}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _provider_from_url(raw: str) -> Provider:
    host = (urlparse(raw.strip()).hostname or "").lower()
    if host == HOSTS["github"]:
        return "github"
    return "bitbucket"


def _validated_repository_url(raw: str, provider: Provider) -> tuple[str, str]:
    url = raw.strip().rstrip("/")
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != HOSTS[provider]
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Use a credential-free HTTPS {provider.title()} URL such as "
                f"https://{HOSTS[provider]}/owner/repository.git."
            ),
        )
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or any(part in (".", "..") for part in parts):
        raise HTTPException(status_code=400, detail=f"The {provider.title()} URL must identify one owner/repository.")
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", repo).strip(".-")
    if not slug:
        raise HTTPException(status_code=400, detail="The repository name is invalid.")
    return url, slug[:100]


def _validated_branch(branch: str) -> str:
    branch = branch.strip()
    if not _BRANCH_RE.fullmatch(branch) or ".." in branch or branch.endswith(("/", ".")):
        raise HTTPException(status_code=400, detail="The branch name is invalid.")
    check = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    if check.returncode:
        raise HTTPException(status_code=400, detail="The branch name is invalid.")
    return branch


def _git_env(provider: Provider, token: str, username: str) -> dict[str, str]:
    askpass = Path(__file__).resolve().parents[2] / "dataos-profile" / "scripts" / "bitbucket_askpass.py"
    env = dict(os.environ)
    env.update(
        {
            "REPOSITORY_PROVIDER": provider,
            "REPOSITORY_TOKEN": token,
            "REPOSITORY_USERNAME": username or DEFAULT_USERNAMES[provider],
            TOKEN_ENVS[provider]: token,
            USERNAME_ENVS[provider]: username or DEFAULT_USERNAMES[provider],
            "GIT_ASKPASS": str(askpass),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "credential.helper",
            "GIT_CONFIG_VALUE_0": "",
        }
    )
    return env


def _run_git(args: list[str], *, env: dict[str, str], cwd: Optional[Path] = None, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _test_remote(provider: Provider, url: str, branch: str, token: str, username: str) -> None:
    result = _run_git(
        ["ls-remote", "--exit-code", "--heads", url, f"refs/heads/{branch}"],
        env=_git_env(provider, token, username),
    )
    if result.returncode:
        raise HTTPException(
            status_code=400,
            detail=f"{provider.title()} authentication failed, the repository is unavailable, or the branch does not exist.",
        )


def _safe_destination(slug: str) -> Path:
    root = _repos_root()
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    destination = root / slug
    if destination.is_symlink() or destination.resolve(strict=False).parent != root:
        raise HTTPException(status_code=400, detail="Unsafe workspace path.")
    return destination


def _prepare(provider: Provider, url: str, slug: str, branch: str, token: str, username: str, commit_name: str, commit_email: str) -> Path:
    destination = _safe_destination(slug)
    env = _git_env(provider, token, username)
    if destination.exists():
        if not (destination / ".git").is_dir():
            raise HTTPException(status_code=409, detail="The workspace path exists but is not a Git repository.")
        origin = _run_git(["remote", "get-url", "origin"], env=env, cwd=destination, timeout=15)
        if origin.returncode or origin.stdout.strip().rstrip("/") != url.rstrip("/"):
            raise HTTPException(status_code=409, detail="The existing workspace belongs to a different repository.")
        result = _run_git(["fetch", "--prune", "origin", branch], env=env, cwd=destination, timeout=180)
    else:
        result = _run_git(
            ["clone", "--single-branch", "--branch", branch, "--", url, str(destination)],
            env=env,
            timeout=300,
        )
    if result.returncode:
        raise HTTPException(status_code=400, detail="Repository preparation failed. Verify access, branch and available disk space.")
    if commit_name.strip():
        _run_git(["config", "user.name", commit_name.strip()], env=env, cwd=destination, timeout=15)
    if commit_email.strip():
        _run_git(["config", "user.email", commit_email.strip()], env=env, cwd=destination, timeout=15)
    return destination


def _status() -> dict:
    from hermes_cli.config import get_env_value_prefer_dotenv

    metadata = _read_metadata()
    provider: Provider = metadata.get("provider") or _provider_from_url(str(metadata.get("repository_url") or ""))
    path = Path(str(metadata.get("workspace_path") or "")) if metadata.get("workspace_path") else None
    return {
        "configured": bool(metadata.get("repository_url")),
        "provider": provider,
        "token_saved": bool(get_env_value_prefer_dotenv(TOKEN_ENVS[provider])),
        "token_saved_by_provider": {
            name: bool(get_env_value_prefer_dotenv(env_name))
            for name, env_name in TOKEN_ENVS.items()
        },
        "repository_url": metadata.get("repository_url", ""),
        "branch": metadata.get("branch", "main"),
        "username": metadata.get("username", DEFAULT_USERNAMES[provider]),
        "commit_name": metadata.get("commit_name", ""),
        "commit_email": metadata.get("commit_email", ""),
        "workspace_path": str(path) if path else "",
        "workspace_ready": bool(path and (path / ".git").is_dir()),
        "vulcan_runtime": "embedded-python3.13",
    }


@router.get("/api/dataos/workspace")
async def get_workspace(profile: Optional[str] = None):
    return await config_scoped_to_thread(profile, _status)


@router.put("/api/dataos/workspace")
async def save_workspace(body: RepositoryWorkspacePut, profile: Optional[str] = None):
    def _save():
        from hermes_cli.config import get_env_value_prefer_dotenv, save_env_value

        provider = body.provider
        url, slug = _validated_repository_url(body.repository_url, provider)
        branch = _validated_branch(body.branch)
        previous = _read_metadata()
        token = body.token.strip() or (get_env_value_prefer_dotenv(TOKEN_ENVS[provider]) or "")
        if not token:
            raise HTTPException(status_code=400, detail=f"Enter a {provider.title()} repository access token.")
        previous_username = previous.get("username") if previous.get("provider", provider) == provider else None
        username = body.username.strip() or str(previous_username or DEFAULT_USERNAMES[provider])
        _test_remote(provider, url, branch, token, username)
        destination = _safe_destination(slug)
        if body.prepare_workspace:
            destination = _prepare(
                provider, url, slug, branch, token, username, body.commit_name, body.commit_email
            )
        # Persist only after the remote and optional clone both succeed.
        save_env_value(PROVIDER_ENV, provider)
        save_env_value(TOKEN_ENVS[provider], token)
        save_env_value(USERNAME_ENVS[provider], username)
        _write_metadata(
            {
                "provider": provider,
                "repository_url": url,
                "branch": branch,
                "username": username,
                "commit_name": body.commit_name.strip(),
                "commit_email": body.commit_email.strip(),
                "workspace_path": str(destination),
            }
        )
        return {**_status(), "connected": True}

    return await config_scoped_to_thread(profile, _save)


@router.post("/api/dataos/workspace/sync")
async def sync_workspace(profile: Optional[str] = None):
    def _sync():
        from hermes_cli.config import get_env_value_prefer_dotenv

        metadata = _read_metadata()
        provider: Provider = metadata.get("provider") or _provider_from_url(str(metadata.get("repository_url") or ""))
        token = get_env_value_prefer_dotenv(TOKEN_ENVS[provider]) or ""
        if not metadata.get("repository_url") or not token:
            raise HTTPException(status_code=400, detail=f"Connect a {provider.title()} repository first.")
        url, slug = _validated_repository_url(str(metadata["repository_url"]), provider)
        branch = _validated_branch(str(metadata.get("branch") or "main"))
        destination = _prepare(
            provider,
            url,
            slug,
            branch,
            token,
            str(metadata.get("username") or DEFAULT_USERNAMES[provider]),
            str(metadata.get("commit_name") or ""),
            str(metadata.get("commit_email") or ""),
        )
        metadata["workspace_path"] = str(destination)
        _write_metadata(metadata)
        return {**_status(), "connected": True}

    return await config_scoped_to_thread(profile, _sync)
