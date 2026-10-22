#!/usr/bin/env python3
"""Offline validation for the DataOS Hermes distribution."""

from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    required = [
        ".no-bundled-skills",
        "distribution.yaml",
        "config.yaml",
        "SOUL.md",
        "skins/botsky.yaml",
        "references/agent-project.schema.json",
        "scripts/prepare_dataos_home.py",
    ]
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit(f"missing required files: {', '.join(missing)}")

    json.loads((ROOT / "references/agent-project.schema.json").read_text())
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    expected_skills = {
        "bitbucket-workspace",
        "build-data-product",
        "dataos-agent-factory",
        "dataos-bot-orchestrator",
        "dataos-cli-operator",
        "data-product-mcp",
        "dataos-evidence",
        "design-data-product",
        "fix-data-product",
        "nilus-pipelines",
    }
    if {path.parent.name for path in skills} != expected_skills:
        raise SystemExit("DataOS skill set does not match the reviewed distribution")
    external_skills = {
        "build-data-product",
        "design-data-product",
        "fix-data-product",
        "nilus-pipelines",
    }
    for path in (path for path in skills if path.parent.name not in external_skills):
        text = path.read_text()
        description = re.search(r"^description: (.+)$", text, re.MULTILINE)
        if not description or len(description.group(1)) > 60 or not description.group(1).endswith("."):
            raise SystemExit(f"invalid skill description: {path}")
        for section in ("## When to Use", "## Prerequisites", "## Procedure", "## Verification"):
            if section not in text:
                raise SystemExit(f"{path} missing {section}")
    for name in external_skills - {"nilus-pipelines"}:
        text = (ROOT / "skills" / name / "SKILL.md").read_text()
        if f"name: {name}" not in text or "/opt/data/hermes/dpbs-docs/" not in text:
            raise SystemExit(f"invalid vendored builder skill: {name}")
    nilus = ROOT / "skills" / "nilus-pipelines"
    if "name: nilus-pipelines" not in (nilus / "SKILL.md").read_text():
        raise SystemExit("invalid vendored Nilus skill")
    for relative in ("SOURCE.md", "references/domain.md", "templates/batch-sample.yml"):
        if not (nilus / relative).is_file():
            raise SystemExit(f"missing Nilus skill material: {relative}")
    docs = ROOT / "dpbs-docs"
    for required_doc in (
        "SOURCE.md",
        "vulcan-docs/README.md",
        "dataos-philosophy/index.md",
        "vulcan-examples/trino",
    ):
        if not (docs / required_doc).exists():
            raise SystemExit(f"missing builder grounding material: {required_doc}")

    config = (ROOT / "config.yaml").read_text()
    soul = (ROOT / "SOUL.md").read_text()
    skin = (ROOT / "skins/botsky.yaml").read_text()
    if "not a general-purpose assistant" not in soul:
        raise SystemExit("SOUL.md is missing the DataOS-only product boundary")
    if "provider: anthropic" not in config or "default: claude-sonnet-4-6" not in config:
        raise SystemExit("Claude Code OAuth must use the reviewed Anthropic default model")
    distribution = (ROOT / "distribution.yaml").read_text()
    if "ANTHROPIC_TOKEN" not in distribution or "OPENAI_API_KEY" in distribution:
        raise SystemExit("distribution must require Claude Code OAuth instead of an OpenAI API key")
    if "display:\n  skin: botsky" not in config:
        raise SystemExit("Botsky skin is not active")
    if 'agent_name: "Botsky Agent"' not in skin or "banner_logo: |" not in skin:
        raise SystemExit("Botsky branding is incomplete")
    for toolset in ("browser", "computer_use", "image_gen", "video_gen", "tts", "messaging"):
        if f"    - {toolset}" not in config:
            raise SystemExit(f"generic toolset is not explicitly disabled: {toolset}")
    for server in ("dataos-cli", "dataproduct-mcp", "dataos-docs"):
        if f"  {server}:" not in config:
            raise SystemExit(f"missing MCP server: {server}")
    for required_setting in (
        'DATAOS_USER_API_KEY: "${DATAOS_USER_API_KEY}"',
        'DATAOS_LOGIN_USER: "${HERMES_DASHBOARD_BASIC_AUTH_USERNAME}"',
        'DATAOS_OWNER_ID: "${DATAOS_OWNER_ID}"',
        'DATAOS_RUN_AS_USER: "${DATAOS_RUN_AS_USER}"',
        'DATAOS_RUN_AS_APIKEY: "${DATAOS_RUN_AS_APIKEY}"',
        'DATAOS_FQDN: "${DATAOS_FQDN}"',
        'DATAOS_TENANT_ID: "${DATAOS_TENANT_ID}"',
        'Authorization: "Bearer ${DATAOS_USER_API_KEY}"',
        'url: "https://sawaniks-081726.instance.dataos.cloud/dataproduct-mcp/api/v1"',
        'command: /opt/hermes/.venv/bin/python',
        'args: [/opt/hermes/dataos-profile/scripts/dataos_mcp_stdio.py]',
        'LOG_LEVEL: "error"',
    ):
        if required_setting not in config:
            raise SystemExit(f"missing DataOS credential boundary: {required_setting}")
    for masked_projection in (
        'DATAOS_RUN_AS_USER: "${DATAOS_USER_ID}"',
        'DATAOS_RUN_AS_APIKEY: "${DATAOS_USER_API_KEY}"',
    ):
        if masked_projection in config:
            raise SystemExit(f"Service credential projection is masked: {masked_projection}")
    if "api_server:\n    enabled: false" not in config:
        raise SystemExit("generic api_server platform must be disabled")
    if "dataos-consumption" in config or "/arguss/mcp/" in config:
        raise SystemExit("retired Arguss consumption MCP is still configured")
    required_tools = (
        "dataos_resource_get",
        "dataos_resource_apply",
        "search",
        "vulcan_quality",
        "vulcan_query_result",
        "searchDocumentation",
    )
    if any(f"- {tool}" not in config and f"[{tool}," not in config for tool in required_tools):
        raise SystemExit("one or more required MCP tools are not explicitly allowlisted")
    forbidden_tools = (
        "dataos_operate_get_secret",
        "dataos_user_apikey",
        "dataos_user_create",
        "dataos_resource_delete",
        "dataos_tenant_delete",
    )
    if any(tool in config for tool in forbidden_tools):
        raise SystemExit("sensitive or destructive MCP tool found in profile allowlist")
    forbidden = ("dGVz" + "dGlu", "YWdlbnRi" + "dWlsZGVy.")
    files = [path for path in ROOT.rglob("*") if path.is_file()]
    for path in files:
        body = path.read_text(errors="ignore")
        if any(value in body for value in forbidden) or re.search(r"\bsk-[A-Za-z0-9_-]{20,}", body):
            raise SystemExit(f"possible credential material in {path}")
    print(f"validated {len(skills)} DataOS skills and 3 MCP connections")


if __name__ == "__main__":
    main()
