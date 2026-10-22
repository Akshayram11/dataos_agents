#!/usr/bin/env python3
"""Private DataOS Agent Builder runtime with server-enforced approval gates."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets as random_secrets
import selectors
import subprocess
import tempfile
import threading
import time
import copy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

HERE = Path(__file__).resolve().parent
SKILLS_DIR = HERE / "skills"
ASSETS = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}

MODEL_PRICING = {
    "inputPerMillion": 0.20,
    "cachedInputPerMillion": 0.02,
    "outputPerMillion": 1.20,
    "currency": "USD",
}

READ_TOOL_NAMES = {
    "dataos_docs_search", "dataos_docs_read", "dataos_schema_get", "dataos_schema_validate",
    "dataos_resource_get", "dataos_resource_runtime_get", "dataos_resource_log",
    "dataos_collation_resource_list", "dataos_collation_resource_get",
}
READ_TOOL_PREFIXES = ("dataos_dp_",)
NEVER_ALLOWED_PARTS = (
    "delete", "secret", "apikey", "tenant_", "user_", "rollback", "rerun", "shell", "exec",
)
MAX_BODY = 512_000
MAX_TOOL_ROUNDS = 14


def config_from_env():
    return {
        "port": int(os.environ.get("PORT", "8080")),
        "fqdn": os.environ.get("AGENT_DATAOS_FQDN", os.environ.get("DATAOS_FQDN", "")).removeprefix("https://").rstrip("/"),
        "owner": os.environ.get("AGENT_OWNER_ID", ""),
        "tenant": os.environ.get("AGENT_TENANT", os.environ.get("DATAOS_TENANT_ID", "engineering")),
        "base_path": os.environ.get("AGENT_BASE_PATH", "/agentbuilder/"),
        "build_id": os.environ.get("AGENT_BUILD_ID", "unknown"),
        "model": os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        "state_file": Path(os.environ.get("STATE_FILE", "/etc/dataos/persist/agent-builder.json")),
        "secrets_file": Path(os.environ.get("SECRETS_FILE", "/etc/dataos/persist/agent-builder-secrets.enc")),
        "runtime_key": os.environ.get("DATAOS_RUN_AS_APIKEY", ""),
        "cli": os.environ.get("DATAOS_CLI", "dataos-ctl"),
    }


def empty_state():
    return {
        "version": 1,
        "conversation": [],
        "prd": None,
        "project": None,
        "deployments": [],
        "usage": {"requests": 0, "input": 0, "cachedInput": 0, "output": 0, "total": 0, "estimatedCostUsd": 0},
        "keyFingerprints": {"dataos": "", "openai": ""},
    }


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    os.chmod(temp, 0o600)
    temp.replace(path)


def load_json(path: Path, fallback):
    try:
        value = json.loads(path.read_text())
        return value if value.get("version") == 1 else fallback
    except FileNotFoundError:
        return fallback


def _crypto_key(runtime_key: str) -> bytes:
    if not runtime_key:
        raise ValueError("Runtime identity is unavailable; encrypted storage is disabled")
    return hashlib.sha256(b"dataos-agent-builder:secrets:v1\0" + runtime_key.encode()).digest()


def _stream(key: bytes, nonce: bytes, size: int) -> bytes:
    chunks, counter = [], 0
    while sum(map(len, chunks)) < size:
        chunks.append(hmac.new(key, b"stream\0" + nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:size]


def encrypt_secrets(path: Path, value: dict, runtime_key: str):
    key = _crypto_key(runtime_key)
    nonce = random_secrets.token_bytes(16)
    plain = json.dumps(value, separators=(",", ":")).encode()
    cipher = bytes(a ^ b for a, b in zip(plain, _stream(key, nonce, len(plain))))
    tag = hmac.new(key, b"tag\0" + nonce + cipher, hashlib.sha256).digest()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {"version": 1, "nonce": base64.b64encode(nonce).decode(), "cipher": base64.b64encode(cipher).decode(), "tag": base64.b64encode(tag).decode()}
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload))
    os.chmod(temp, 0o600)
    temp.replace(path)


def decrypt_secrets(path: Path, runtime_key: str):
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    key = _crypto_key(runtime_key)
    nonce, cipher, tag = (base64.b64decode(payload[name]) for name in ("nonce", "cipher", "tag"))
    expected = hmac.new(key, b"tag\0" + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("Stored credentials could not be authenticated")
    plain = bytes(a ^ b for a, b in zip(cipher, _stream(key, nonce, len(cipher))))
    return json.loads(plain)


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def redact(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    text = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED_API_KEY]", text)
    text = re.sub(r"(?i)(apikey|api_key|token)(\s*[=:]\s*)[^\s,}\]]+", r"\1\2[REDACTED]", text)
    return text[:100_000]


def safe_path(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,159}", value)) and ".." not in value and not value.startswith("/")


def manifest_identity(manifest: dict):
    return (str(manifest.get("type", "")), str(manifest.get("version", "")), str(manifest.get("name", "")))


def tool_failed(result) -> bool:
    if not isinstance(result, dict):
        return True
    if result.get("isError"):
        return True
    text = json.dumps(result).lower()
    return bool(re.search(
        r"crashloopbackoff|(?:aggregate.?status|phase|status)[^a-z0-9]{0,8}(?:failed|error|unhealthy)", text
    ))


def validate_project(project: dict):
    if not isinstance(project, dict):
        raise ValueError("Generated project is not an object")
    name = str(project.get("project_name", ""))
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,47}", name):
        raise ValueError("Generated project_name is invalid")
    files = project.get("files", [])
    resources = project.get("resources", [])
    if not isinstance(files, list) or len(files) > 40 or not isinstance(resources, list) or not resources or len(resources) > 20:
        raise ValueError("Generated project has invalid artifact counts")
    total = 0
    for item in files:
        if not isinstance(item, dict) or not safe_path(str(item.get("path", ""))):
            raise ValueError("Generated file path is unsafe")
        total += len(str(item.get("content", "")))
    identities = []
    for item in resources:
        manifest = item.get("manifest") if isinstance(item, dict) else None
        if not isinstance(manifest, dict):
            raise ValueError("Every generated resource must contain a JSON manifest object")
        resource_type, version, resource_name = manifest_identity(manifest)
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", resource_type) or resource_type in {"secret", "grant", "policy", "user", "tenant"}:
            raise ValueError("Generated resource type is forbidden")
        if not re.fullmatch(r"v[0-9]+(?:alpha|beta)?", version) or not re.fullmatch(r"[a-z][a-z0-9-]{1,47}", resource_name):
            raise ValueError("Generated resource identity is invalid")
        computed = f"{resource_type}:{version}:{resource_name}"
        if item.get("identifier") != computed:
            raise ValueError("Generated resource identifier does not match its manifest")
        identities.append(computed)
        total += len(json.dumps(manifest))
    if total > 300_000:
        raise ValueError("Generated project is too large")
    order = project.get("deploy_order", [])
    if sorted(order) != sorted(identities):
        raise ValueError("deploy_order must contain every generated resource exactly once")
    project["identities"] = identities
    return project


def derive_access_plan(project: dict, owner: str, tenant: str):
    run_as, computes, paths = set(), set(), set()
    for item in project["resources"]:
        manifest = item["manifest"]
        spec = manifest.get("spec") or {}
        if spec.get("runAsUser"):
            run_as.add(str(spec["runAsUser"]))
        if spec.get("compute"):
            computes.add(str(spec["compute"]))
        http = spec.get("http") or {}
        if http.get("enabled") and http.get("path"):
            paths.add(str(http["path"]))
    if len(run_as) != 1:
        raise ValueError("Generated resources must use exactly one application identity")
    application_id = next(iter(run_as))
    if application_id == owner or not re.fullmatch(r"[a-z][a-z0-9]{2,47}", application_id):
        raise ValueError("Generated runAsUser must be a distinct application identity")
    if not computes or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in computes):
        raise ValueError("Generated resources must use an explicit valid compute")
    if any(not re.fullmatch(r"/[A-Za-z0-9/_-]{1,120}", value) for value in paths):
        raise ValueError("Generated ingress path is invalid")
    policies = []
    for index, compute in enumerate(sorted(computes), 1):
        policies.append({
            "name": f"built-{application_id}-compute-{index}", "collection": tenant,
            "description": f"Allow generated application {application_id} to use {compute}",
            "subjects": {"tags": [f"users:id:{application_id}"]}, "predicates": ["read", "use"],
            "objects": {"tags": [[f"dataos:resource:compute:v2alpha:{compute}"]]}, "allow": True,
        })
    policies.extend([
        {"name": f"built-{application_id}-compute-runtime-use", "collection": tenant,
         "description": "Authorize runtime compute use check", "subjects": {"tags": [f"users:id:{application_id}"]},
         "predicates": ["use"], "objects": {"tags": [["dataos:resource:compute"]]}, "allow": True},
        {"name": f"built-{application_id}-compute-runtime-read", "collection": tenant,
         "description": "Authorize runtime compute read check", "subjects": {"tags": [f"users:id:{application_id}"]},
         "predicates": ["read"], "objects": {"tags": [["dataos:resource:compute"]]}, "allow": True},
        {"name": f"built-{application_id}-owner-run-as", "collection": tenant,
         "description": "Allow the approved owner to deploy the generated application identity",
         "subjects": {"tags": [f"users:id:{owner}"]}, "predicates": ["run_as"],
         "objects": {"tags": [[f"users:id:{application_id}"]]}, "allow": True},
    ])
    if paths:
        ingress_paths = sorted({entry for path in paths for entry in (path, path.rstrip("/") + "/**")})
        policies.append({"name": f"built-{application_id}-private-ingress", "collection": "system",
                         "description": "Allow only the approved owner to open the generated application",
                         "subjects": {"tags": [f"users:id:{owner}"]}, "predicates": ["get", "post"],
                         "objects": {"paths": ingress_paths}, "allow": True})
    return {"applicationId": application_id, "computes": sorted(computes), "paths": sorted(paths), "policies": policies}


class McpSession:
    def __init__(self, cfg: dict, dataos_key: str):
        env = dict(os.environ)
        env.update({"DATAOS_RUN_AS_USER": cfg["owner"], "DATAOS_RUN_AS_APIKEY": dataos_key, "NO_COLOR": "1"})
        self.process = subprocess.Popen(
            [cfg["cli"], "develop", "assist", "mcp", "run"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, env=env,
        )
        self.lock = threading.Lock()
        self.next_id = 0
        self.request("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "dataos-agent-builder", "version": "1.0.0"}}, 40)
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _write(self, payload):
        if self.process.poll() is not None:
            raise RuntimeError("DataOS CLI MCP exited unexpectedly")
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params=None, timeout=60):
        with self.lock:
            self.next_id += 1
            request_id = self.next_id
            self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
            selector = selectors.DefaultSelector()
            selector.register(self.process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                events = selector.select(max(0.1, deadline - time.monotonic()))
                if not events:
                    continue
                line = self.process.stdout.readline()
                if not line:
                    break
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if value.get("id") != request_id:
                    continue
                if value.get("error"):
                    raise RuntimeError(value["error"].get("message", "MCP request failed"))
                return value.get("result", {})
            raise TimeoutError(f"DataOS CLI MCP timed out during {method}")

    def list_tools(self):
        return self.request("tools/list", timeout=40).get("tools", [])

    def call(self, name: str, arguments: dict, timeout=120):
        return self.request("tools/call", {"name": name, "arguments": arguments}, timeout)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(3)
            except subprocess.TimeoutExpired:
                self.process.kill()


def is_read_tool(tool: dict) -> bool:
    name = str(tool.get("name", ""))
    annotations = tool.get("annotations") or {}
    named = name in READ_TOOL_NAMES or any(name.startswith(prefix) for prefix in READ_TOOL_PREFIXES)
    forbidden = any(part in name.lower() for part in NEVER_ALLOWED_PARTS)
    return named and not forbidden and annotations.get("readOnlyHint") is True and annotations.get("destructiveHint") is not True


class BuilderApp:
    def __init__(self, cfg=None):
        self.cfg = cfg or config_from_env()
        self.state = load_json(self.cfg["state_file"], empty_state())
        self.secrets = decrypt_secrets(self.cfg["secrets_file"], self.cfg["runtime_key"])
        self.state_lock = threading.RLock()
        self.mcp = None
        self.tools = []
        self.skill_text = "\n\n".join(path.read_text() for path in sorted(SKILLS_DIR.glob("*/SKILL.md")))
        if self.secrets:
            try:
                self._connect_mcp()
            except Exception:
                self.mcp = None
                self.tools = []

    def _save(self):
        atomic_json(self.cfg["state_file"], self.state)

    def _connect_mcp(self):
        if self.mcp:
            self.mcp.close()
        self.mcp = McpSession(self.cfg, self.secrets["dataosKey"])
        catalog = self.mcp.list_tools()
        self.tools = [tool for tool in catalog if is_read_tool(tool)]
        names = {tool.get("name") for tool in catalog}
        required = {"dataos_resource_apply", "dataos_resource_get", "dataos_schema_validate", "dataos_user_create"}
        if not required.issubset(names) or not self.tools:
            raise RuntimeError("DataOS CLI MCP is missing required builder tools")

    def _openai(self, payload: dict, timeout=120):
        request = Request("https://api.openai.com/v1/responses", data=json.dumps(payload).encode(), method="POST", headers={
            "Authorization": f"Bearer {self.secrets['openaiKey']}", "Content-Type": "application/json",
        })
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read())
        except HTTPError as error:
            detail = json.loads(error.read() or b"{}").get("error", {}).get("message", f"OpenAI HTTP {error.code}")
            raise RuntimeError(redact(detail)) from error
        usage = result.get("usage") or {}
        inp, out = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        cached = min(inp, int((usage.get("input_tokens_details") or {}).get("cached_tokens", 0)))
        meter = self.state["usage"]
        meter["requests"] += 1; meter["input"] += inp; meter["cachedInput"] += cached; meter["output"] += out
        meter["total"] += int(usage.get("total_tokens", inp + out))
        meter["estimatedCostUsd"] += ((inp - cached) * .20 + cached * .02 + out * 1.20) / 1_000_000
        return result

    def _heimdall(self, path: str, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode()
        request = Request(f"https://{self.cfg['fqdn']}{path}", data=data, method=method, headers={
            "Authorization": f"Bearer {self.secrets['dataosKey']}", "Content-Type": "application/json",
        })
        try:
            with urlopen(request, timeout=40) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except HTTPError as error:
            raw = error.read()
            try: payload = json.loads(raw) if raw else None
            except json.JSONDecodeError: payload = None
            return error.code, payload

    def _provision_access(self, plan: dict):
        application_id = plan["applicationId"]
        status, user = self._heimdall(f"/heimdall/api/v1/users/{application_id}")
        if status == 404:
            created = self.mcp.call("dataos_user_create", {"name": application_id, "type": "application", "user_id": application_id}, 120)
            if created.get("isError"):
                raise RuntimeError(f"Application identity creation failed: {redact(created)}")
            identity = "created"
        elif status == 200 and isinstance(user, dict) and user.get("type") == "application":
            identity = "existing"
        else:
            raise RuntimeError("Generated runAsUser exists but is not an application identity")
        status, actual = self._heimdall("/heimdall/api/v1/policies")
        if status != 200 or not isinstance(actual, list):
            raise RuntimeError("Cannot inspect existing access policies")
        actual = {policy.get("name"): policy for policy in actual}
        created, unchanged = [], []
        for policy in plan["policies"]:
            old = actual.get(policy["name"])
            if old is not None:
                if any(old.get(key) != value for key, value in policy.items()):
                    raise RuntimeError(f"Existing access policy differs: {policy['name']}")
                unchanged.append(policy["name"]); continue
            status, _ = self._heimdall("/heimdall/api/v1/policies", "POST", policy)
            if status != 201:
                raise RuntimeError(f"Access policy creation failed: {policy['name']} (HTTP {status})")
            created.append(policy["name"])
        return {"identity": identity, "applicationId": application_id, "policiesCreated": created, "policiesUnchanged": unchanged}

    def _evidence(self, identifier: str):
        evidence = {}
        calls = [
            ("resource", "dataos_resource_get", {"identifier": identifier, "details": True}),
            ("runtime", "dataos_resource_runtime_get", {"identifier": identifier, "details": True}),
            ("logs", "dataos_resource_log", {"identifier": identifier, "tail_lines": 80}),
        ]
        for label, tool, arguments in calls:
            try: evidence[label] = self.mcp.call(tool, arguments, 120)
            except Exception as error: evidence[label] = {"isError": True, "message": redact(str(error))}
        return evidence

    def _repair_manifest(self, project: dict, item: dict, evidence: dict):
        original = item["manifest"]
        prompt = (
            "Return only one corrected JSON DataOS manifest object. Preserve type, version, name, runAsUser, compute, ingress paths, tool/security boundary, and intended behavior. "
            "Make the smallest correction supported by the evidence. Do not add permissions, secrets, users, policies, deletion, force, cascade, rollback, or new resources.\n\n"
            f"ORIGINAL MANIFEST:\n{json.dumps(original)}\n\nBOUNDED EVIDENCE:\n{redact(evidence)}"
        )
        text, _ = self._agent([{"role": "user", "content": prompt}], "repair", False, 7000)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
        repaired = json.loads(cleaned)
        if manifest_identity(repaired) != manifest_identity(original):
            raise RuntimeError("Repair changed the resource identity")
        candidate = copy.deepcopy(project)
        target = next(resource for resource in candidate["resources"] if resource["identifier"] == item["identifier"])
        target["manifest"] = repaired
        validate_project(candidate)
        new_plan = derive_access_plan(candidate, self.cfg["owner"], self.cfg["tenant"])
        if new_plan != project["accessPlan"]:
            raise RuntimeError("Repair attempted to change the approved access plan")
        lint = self.mcp.call("dataos_resource_apply", {"yaml_content": json.dumps(repaired), "lint": True, "disable_interpolation": True})
        if lint.get("isError"):
            raise RuntimeError("Repaired manifest did not pass schema lint")
        return repaired

    @staticmethod
    def _output_text(payload):
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"].strip()
        parts = []
        for item in payload.get("output", []):
            if item.get("type") == "message":
                parts.extend(content.get("text", "") for content in item.get("content", []))
        return "\n".join(parts).strip()

    def _instructions(self, mode="discovery"):
        gate = {
            "discovery": "Gather requirements one focused question at a time. Use read-only tools only when platform evidence helps. Do not produce deployable artifacts yet.",
            "prd": "Produce the complete approval-ready PRD now. Do not claim it is approved and do not deploy.",
            "generate": "Generate a complete project JSON matching the requested schema. Do not deploy it.",
            "repair": "Return only a corrected manifest object for the same resource identity. Make the smallest evidence-backed correction.",
        }[mode]
        return (
            f"You are the private DataOS Agent Builder for {self.cfg['owner']} in tenant {self.cfg['tenant']}.\n"
            "You help design secure AI agents on DataOS. Use only facts explicitly supplied by the user, evidence returned by the connected tools, or source-identified bundled documentation. "
            "Never introduce generic environment names, lifecycle stages, platform components, resource types, roles, approval authorities, permissions, or capabilities as DataOS facts. "
            "Do not rely on general model knowledge for DataOS claims. If a platform fact cannot be verified, label it Unverified; do not turn it into an assumption or an invented choice. "
            "Distinguish User requirement, Verified platform fact, and Recommendation in every design response. "
            "Never request credentials in chat. Never call or suggest destructive tools. A chat message is not deployment approval.\n"
            f"Current mode: {mode}. {gate}\n\n{self.skill_text[:70000]}"
        )

    def _function_tools(self):
        return [{"type": "function", "name": tool["name"], "description": str(tool.get("description", ""))[:8000],
                 "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}}, "strict": False}
                for tool in self.tools]

    def _agent(self, messages: list, mode="discovery", tools=True, max_output=2600):
        if not self.secrets or not self.mcp:
            raise RuntimeError("Connect valid DataOS and OpenAI API keys first")
        input_items = [{"role": item["role"], "content": item["content"]} for item in messages[-24:]]
        trace = []
        for _ in range(MAX_TOOL_ROUNDS):
            body = {"model": self.cfg["model"], "instructions": self._instructions(mode), "input": input_items,
                    "max_output_tokens": max_output, "store": False}
            if tools:
                body.update({"tools": self._function_tools(), "tool_choice": "auto"})
            response = self._openai(body)
            calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
            if not calls:
                answer = self._output_text(response)
                if not answer:
                    raise RuntimeError("The model returned no answer")
                return answer, trace
            outputs = []
            for call in calls:
                if call.get("name") not in {tool["name"] for tool in self.tools}:
                    raise RuntimeError("The model requested a blocked tool")
                arguments = json.loads(call.get("arguments") or "{}")
                result = self.mcp.call(call["name"], arguments)
                trace.append({"tool": call["name"], "arguments": arguments})
                outputs.append({"type": "function_call_output", "call_id": call["call_id"], "output": redact(result)})
            input_items.extend(response.get("output", [])); input_items.extend(outputs)
        raise RuntimeError("The agent reached its read-only tool-round limit")

    def public_state(self):
        with self.state_lock:
            return {
                "owner": self.cfg["owner"], "tenant": self.cfg["tenant"], "model": self.cfg["model"],
                "ready": bool(self.secrets and self.mcp), "toolCount": len(self.tools),
                "conversation": self.state["conversation"], "prd": self.state["prd"], "project": self.state["project"],
                "deployments": self.state["deployments"][-10:], "usage": self.state["usage"], "pricing": MODEL_PRICING,
            }

    def save_keys(self, dataos_key: str, openai_key: str):
        if not (20 <= len(dataos_key) <= 4096 and not re.search(r"\s", dataos_key)):
            raise ValueError("Invalid DataOS API key")
        if not (20 <= len(openai_key) <= 512 and not re.search(r"\s", openai_key)):
            raise ValueError("Invalid OpenAI API key")
        old = self.secrets
        self.secrets = {"dataosKey": dataos_key, "openaiKey": openai_key}
        try:
            self._connect_mcp()
        except Exception:
            self.secrets = old
            raise ValueError("DataOS CLI MCP rejected this key or could not initialize")
        request = Request(f"https://api.openai.com/v1/models/{self.cfg['model']}", headers={"Authorization": f"Bearer {openai_key}"})
        try:
            with urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise ValueError("OpenAI model validation failed")
        except (HTTPError, URLError) as error:
            self.mcp.close(); self.mcp = None; self.tools = []; self.secrets = old
            if old:
                try: self._connect_mcp()
                except Exception: self.mcp = None; self.tools = []
            raise ValueError("OpenAI rejected this key or model access is unavailable") from error
        encrypt_secrets(self.cfg["secrets_file"], self.secrets, self.cfg["runtime_key"])
        self.state["keyFingerprints"] = {"dataos": fingerprint(dataos_key), "openai": fingerprint(openai_key)}
        self._save()
        return {"message": f"Connected securely. {len(self.tools)} read-only planning tools available."}

    def chat(self, message: str):
        message = message.strip()
        if not (1 <= len(message) <= 8000):
            raise ValueError("Message must be between 1 and 8000 characters")
        with self.state_lock:
            history = self.state["conversation"]
            answer, trace = self._agent([*history, {"role": "user", "content": message}], "discovery")
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            history.extend([{"role": "user", "content": message, "at": now}, {"role": "assistant", "content": answer, "trace": trace, "at": now}])
            self.state["conversation"] = history[-40:]
            if self.state.get("prd"):
                self.state["prd"]["status"] = "stale"
                self.state["project"] = None
            self._save()
            return {"answer": answer, "trace": trace}

    def generate_prd(self):
        with self.state_lock:
            if not self.state["conversation"]:
                raise ValueError("Describe the agent before generating a PRD")
            prompt = {"role": "user", "content": "Generate the complete concise PRD now from our discovery. Keep unknown platform facts explicitly Unverified; do not turn them into assumptions. Label non-platform proposals as Recommendations. Include provenance for DataOS-specific claims. Do not ask another question."}
            content, trace = self._agent([*self.state["conversation"], prompt], "prd", True, 4200)
            revision = hashlib.sha256(content.encode()).hexdigest()[:16]
            self.state["prd"] = {"revision": revision, "status": "draft", "content": content, "trace": trace, "createdAt": time.time()}
            self.state["project"] = None
            self._save()
            return self.state["prd"]

    def approve_prd(self, revision: str):
        with self.state_lock:
            prd = self.state.get("prd")
            if not prd or prd.get("revision") != revision or prd.get("status") not in {"draft", "stale"}:
                raise ValueError("PRD revision does not match the current draft")
            if prd.get("status") == "stale":
                raise ValueError("Requirements changed; generate a fresh PRD")
            prd["status"] = "approved"; prd["approvedAt"] = time.time()
            self._save()
            return prd

    def generate_project(self):
        with self.state_lock:
            prd = self.state.get("prd")
            if not prd or prd.get("status") != "approved":
                raise ValueError("Approve the current PRD before generating artifacts")
            schema = (
                "Return only JSON with keys project_name, summary, files, resources, deploy_order, verification. "
                "files is an array of {path,content}. resources is an array of {identifier,manifest}, where manifest is a JSON DataOS resource object. "
                "deploy_order contains every identifier exactly once in dependency order. Do not generate secret, grant, policy, user, or tenant resources. "
                "Use the pinned dataos-ctl-agent runtime for agents that need platform tools. Include README.md and skills/*/SKILL.md files. "
                "Every generated resource that supports runAsUser must use one shared lowercase application identity distinct from the human owner, and runnable resources must name an explicit compute. "
                "For Vulcan data-product design/build/fix projects, include the official `npx dataproduct-builder-skills@latest` setup, the approved engine choice, and route work through its generated design/build/fix skills. "
                "The project must be owner-private, least privilege, and must not contain credential values.\n\nAPPROVED PRD:\n" + prd["content"]
            )
            text, trace = self._agent([{"role": "user", "content": schema}], "generate", False, 10000)
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
            project = validate_project(json.loads(cleaned))
            project["accessPlan"] = derive_access_plan(project, self.cfg["owner"], self.cfg["tenant"])
            lint = []
            for identifier in project["deploy_order"]:
                item = next(resource for resource in project["resources"] if resource["identifier"] == identifier)
                result = self.mcp.call("dataos_resource_apply", {"yaml_content": json.dumps(item["manifest"]), "lint": True, "disable_interpolation": True})
                if result.get("isError"):
                    raise ValueError(f"Generated manifest failed lint: {identifier}: {redact(result)}")
                lint.append({"identifier": identifier, "ok": True})
            project.update({"revision": hashlib.sha256(cleaned.encode()).hexdigest()[:16], "prdRevision": prd["revision"], "status": "validated", "trace": trace, "lint": lint})
            self.state["project"] = project
            self._save()
            return project

    def deploy(self, revision: str, confirmation: str):
        with self.state_lock:
            project, prd = self.state.get("project"), self.state.get("prd")
            if not project or project.get("revision") != revision or project.get("status") != "validated":
                raise ValueError("Generated project revision is not deployable")
            if not prd or prd.get("status") != "approved" or project.get("prdRevision") != prd.get("revision"):
                raise ValueError("PRD approval is missing or stale")
            expected = f"DEPLOY {project['project_name']}"
            if not hmac.compare_digest(confirmation.strip(), expected):
                raise ValueError(f"Type {expected} to authorize this deployment")
            report = {"id": uuid.uuid4().hex, "startedAt": time.time(), "projectRevision": revision, "resources": [], "status": "running"}
            self.state["deployments"].append(report); self._save()
            try:
                report["access"] = self._provision_access(project["accessPlan"])
                self._save()
                for identifier in project["deploy_order"]:
                    item = next(resource for resource in project["resources"] if resource["identifier"] == identifier)
                    manifest = item["manifest"]
                    entry = {"identifier": identifier, "healthy": False, "attempts": []}
                    report["resources"].append(entry)
                    for attempt in range(3):
                        applied = self.mcp.call("dataos_resource_apply", {"yaml_content": json.dumps(manifest), "lint": False, "disable_interpolation": True}, 180)
                        evidence = self._evidence(identifier)
                        failed = tool_failed(applied) or tool_failed(evidence["resource"])
                        if identifier.split(":", 1)[0] in {"service", "worker", "workflow"}:
                            failed = failed or tool_failed(evidence["runtime"])
                        entry["attempts"].append({"number": attempt + 1, "apply": redact(applied), "evidence": redact(evidence), "failed": failed})
                        self._save()
                        if not failed:
                            entry["healthy"] = True; entry["finalManifest"] = manifest; break
                        if attempt == 2:
                            entry["error"] = "Deployment remained unhealthy after two safe corrections"
                            raise RuntimeError(f"Deployment verification failed for {identifier}")
                        manifest = self._repair_manifest(project, item, evidence)
                        entry.setdefault("repairs", []).append({"attempt": attempt + 1, "manifest": manifest})
                    self._save()
                report["status"] = "verified" if all(item["healthy"] for item in report["resources"]) else "needs-attention"
            except Exception as error:
                report["status"] = "failed"; report["error"] = redact(str(error))
            report["finishedAt"] = time.time(); self._save()
            return report

    def reset(self):
        with self.state_lock:
            usage = self.state["usage"]; fingerprints = self.state["keyFingerprints"]
            self.state = empty_state(); self.state["usage"] = usage; self.state["keyFingerprints"] = fingerprints
            self._save()


def browser_tokens(handler):
    values = []
    authorization = handler.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        values.append(authorization[7:].strip())
    for name in ("x-dataos-token", "x-auth-token", "x-forwarded-access-token"):
        if handler.headers.get(name): values.append(handler.headers[name].strip())
    for part in handler.headers.get("Cookie", "").split(";"):
        if "=" in part:
            value = part.split("=", 1)[1].strip()
            if 20 <= len(value) <= 4096:
                values.append(value)
    return list(dict.fromkeys(values))[:12]


def owner_session(cfg, lifetime=28_800):
    payload = base64.urlsafe_b64encode(json.dumps({
        "owner": cfg["owner"], "exp": int(time.time()) + lifetime,
    }, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(cfg["runtime_key"].encode(), b"agent-builder-owner-session-v1\0" + payload.encode(), hashlib.sha256).digest()
    return payload + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def valid_owner_session(token, cfg):
    if not token or not cfg.get("runtime_key"):
        return False
    try:
        payload, encoded_signature = token.split(".", 1)
        expected = hmac.new(cfg["runtime_key"].encode(), b"agent-builder-owner-session-v1\0" + payload.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
        value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return (hmac.compare_digest(expected, supplied) and value.get("owner") == cfg["owner"]
                and int(value.get("exp", 0)) >= int(time.time()))
    except (ValueError, TypeError, json.JSONDecodeError):
        return False


def authorize_owner_token(token, cfg):
    if not token or not cfg["owner"] or not cfg["fqdn"]:
        return False
    request = Request(f"https://{cfg['fqdn']}/heimdall/api/v1/authorize", data=json.dumps({"token": token}).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            value = json.loads(response.read())
        return bool(value.get("valid") and value.get("allow") and (value.get("result") or {}).get("id") == cfg["owner"])
    except Exception:
        return False


def authorize_owner_key(token, cfg, opener=urlopen):
    """Prove an API key is one of the configured owner's Heimdall tokens."""
    if not token or not cfg["owner"] or not cfg["fqdn"]:
        return False
    request = Request(
        f"https://{cfg['fqdn']}/heimdall/api/v1/users/{cfg['owner']}/tokens",
        headers={"Authorization": f"Bearer {token}", "apikey": token, "Accept": "application/json"},
    )
    try:
        with opener(request, timeout=10) as response:
            values = json.loads(response.read())
        if not isinstance(values, list):
            return False
        for value in values:
            data = value.get("data") or {}
            if value.get("user_id") == cfg["owner"] and data.get("apikey") == token:
                return True
    except Exception:
        return False
    return False


def authorize(handler, cfg):
    if not cfg["owner"] or not cfg["fqdn"]:
        return False
    for part in handler.headers.get("Cookie", "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == "agent_builder_owner" and valid_owner_session(value, cfg):
            return True
    for token in browser_tokens(handler):
        if authorize_owner_token(token, cfg):
            return True
    return False


class Handler(BaseHTTPRequestHandler):
    server_version = "DataOSAgentBuilder/1.0"

    def _json(self, status, value, headers=None):
        payload = json.dumps(value).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "SAMEORIGIN")
        for name, header_value in (headers or {}).items(): self.send_header(name, header_value)
        self.end_headers(); self.wfile.write(payload)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY: raise ValueError("Request body is too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def _private(self):
        if not authorize(self, self.server.app.cfg):
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "Owner authentication required"}); return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/healthz":
            self._json(200, {"ok": True, "buildId": self.server.app.cfg["build_id"]}); return
        if path in ASSETS:
            asset = HERE / ASSETS[path]
            payload = asset.read_bytes()
            self.send_response(200); self.send_header("Content-Type", mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        if path == "/api/state" and self._private():
            self._json(200, self.server.app.public_state()); return
        self._json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/settings/keys":
            try:
                if self.headers.get("Sec-Fetch-Site", "same-origin") == "cross-site":
                    self._json(403, {"error": "Cross-site request rejected"}); return
                body = self._body(); app = self.server.app
                dataos_key = str(body.get("dataosKey", "")).strip()
                result = app.save_keys(dataos_key, str(body.get("openaiKey", "")).strip())
                cookie = f"agent_builder_owner={owner_session(app.cfg)}; Path={app.cfg['base_path']}; Max-Age=28800; HttpOnly; Secure; SameSite=Strict"
                self._json(200, result, {"Set-Cookie": cookie}); return
            except (ValueError, json.JSONDecodeError) as error:
                self._json(400, {"error": redact(str(error))}); return
            except Exception as error:
                self._json(500, {"error": redact(str(error))}); return
        if not self._private(): return
        try:
            body = self._body(); app = self.server.app
            if path == "/api/chat": result = app.chat(str(body.get("message", "")))
            elif path == "/api/prd/generate": result = app.generate_prd()
            elif path == "/api/prd/approve": result = app.approve_prd(str(body.get("revision", "")))
            elif path == "/api/project/generate": result = app.generate_project()
            elif path == "/api/deploy": result = app.deploy(str(body.get("revision", "")), str(body.get("confirmation", "")))
            elif path == "/api/reset": app.reset(); result = {"ok": True}
            else: self._json(404, {"error": "Not found"}); return
            self._json(200, result)
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": redact(str(error))})
        except Exception as error:
            self._json(500, {"error": redact(str(error))})

    def log_message(self, format, *args):
        return


def main():
    app = BuilderApp()
    server = ThreadingHTTPServer(("0.0.0.0", app.cfg["port"]), Handler)
    server.app = app
    print(json.dumps({"event": "ready", "port": app.cfg["port"], "owner": app.cfg["owner"], "tenant": app.cfg["tenant"], "buildId": app.cfg["build_id"]}), flush=True)
    try:
        server.serve_forever()
    finally:
        if app.mcp: app.mcp.close()


if __name__ == "__main__":
    main()
