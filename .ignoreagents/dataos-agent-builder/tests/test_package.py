"""Offline package, security-boundary, and workflow tests."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load_module("builder_installer", ROOT / "install.py")
runtime = load_module("builder_runtime", ROOT / "runtime/server.py")


class PackageChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.area = Path(self.tmp.name)
        self.config = json.loads((ROOT / "environment.example.json").read_text())
        self.path = self.area / "environment.json"; self.path.write_text(json.dumps(self.config))
        self.cli_dir = self.area / "cli"; (self.cli_dir / "sawan-rn").mkdir(parents=True)
        (self.cli_dir / "dataos.context.yaml").write_text("current_context_name: sawan-rn\n")
        (self.cli_dir / "sawan-rn/.dataos.tenancy.config.yaml").write_text(
            "dataos_fqdn: sawaniks-081726.instance.dataos.cloud\ndataos_tenant: engineering\n")

    def load(self):
        return installer.configuration(self.path, "/usr/bin/true", str(self.cli_dir))

    def test_render_is_private_stateful_and_uses_pinned_cli_agent_image(self):
        service, link, policies = installer.render(self.load(), self.area / "rendered")
        self.assertEqual(service["spec"]["runAsUser"], "agentbuilder")
        self.assertEqual(service["spec"]["disk"]["mountPath"], "/etc/dataos/persist")
        self.assertTrue(service["spec"]["http"]["noNetworkAuthorization"])
        self.assertIn("tmdcio/dataos-ctl-agent:3.25.0-dev@sha256:", service["spec"]["stackSpec"]["image"])
        self.assertEqual(link["owner"], "akshaychametmdcio")
        self.assertEqual(link["spec"]["link"]["owners"], ["akshaychametmdcio"])
        self.assertNotIn("@@", json.dumps([service, link, policies]))
        boot = service["spec"]["stackSpec"]["arguments"][0]
        payloads = [base64.b64decode(value).decode() for value in re.findall(r"printf '%s' '([A-Za-z0-9+/=]+)' \| base64 -d", boot)]
        packed = "\n".join(payloads)
        for skill in ("requirements-discovery", "platform-architecture", "agent-prd", "security-boundary", "deploy-and-diagnose", "data-product-builder-routing"):
            self.assertIn(skill, packed)
        self.assertIn("server-enforced approval gates", packed)
        script = self.area / "bootstrap.sh"; script.write_text(boot)
        subprocess.run(["bash", "-n", str(script)], check=True)

    def test_application_identity_has_no_platform_write_grants(self):
        _, _, policies = installer.render(self.load(), self.area / "rendered")
        application = [policy for policy in policies if "users:id:agentbuilder" in policy["subjects"]["tags"]]
        predicates = {predicate for policy in application for predicate in policy["predicates"]}
        self.assertEqual(predicates, {"read", "use"})
        self.assertTrue({"delete", "create", "update", "post", "put"}.isdisjoint(predicates))

    def test_owner_is_exact_and_target_mismatch_fails_closed(self):
        for invalid in ("*", "akshay*", "agentbuilder"):
            self.path.write_text(json.dumps(dict(self.config, operator_id=invalid)))
            with self.assertRaises(ValueError): self.load()
        self.path.write_text(json.dumps(self.config))
        platform = installer.load_platform(); config = self.load(); platform.verify_target(config)
        with self.assertRaises(ValueError): platform.verify_target(dict(config, tenant="wrong"))


class RuntimeChecks(unittest.TestCase):
    def test_encrypted_secrets_round_trip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as area:
            path = Path(area) / "keys.enc"
            runtime.encrypt_secrets(path, {"dataosKey": "d" * 30, "openaiKey": "sk-" + "o" * 30}, "runtime-key")
            self.assertEqual(runtime.decrypt_secrets(path, "runtime-key")["dataosKey"], "d" * 30)
            payload = json.loads(path.read_text()); payload["cipher"] = base64.b64encode(b"tampered").decode(); path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError): runtime.decrypt_secrets(path, "runtime-key")

    def test_read_tool_filter_blocks_mutating_and_secret_tools(self):
        annotation = {"readOnlyHint": True, "destructiveHint": False}
        self.assertTrue(runtime.is_read_tool({"name": "dataos_docs_search", "annotations": annotation}))
        self.assertTrue(runtime.is_read_tool({"name": "dataos_dp_quality", "annotations": annotation}))
        self.assertTrue(runtime.is_read_tool({"name": "dataos_resource_runtime_get", "annotations": annotation}))
        for name in ("dataos_resource_apply", "dataos_resource_delete", "dataos_operate_get_secret", "dataos_user_get"):
            self.assertFalse(runtime.is_read_tool({"name": name, "annotations": annotation}))

    def test_runtime_failure_detection_is_bounded_to_clear_failure_signals(self):
        self.assertTrue(runtime.tool_failed({"isError": True, "content": []}))
        self.assertTrue(runtime.tool_failed({"content": [{"text": "phase: failed"}]}))
        self.assertFalse(runtime.tool_failed({"content": [{"text": "phase: running"}]}))
        self.assertFalse(runtime.tool_failed({"content": [{"text": "checks: 10 passed, 0 failed"}]}))
        self.assertFalse(runtime.tool_failed({"content": [{"text": "phase: pending"}]}))

    def test_project_validation_enforces_safe_identity_and_exact_order(self):
        project = {"project_name": "quality-agent", "summary": "x", "files": [{"path": "skills/quality/SKILL.md", "content": "ok"}],
                   "resources": [{"identifier": "service:v2alpha:quality-agent", "manifest": {"type": "service", "version": "v2alpha", "name": "quality-agent", "spec": {"runAsUser": "qualityagent", "compute": "engineering-compute", "http": {"enabled": True, "path": "/quality-agent"}}}}],
                   "deploy_order": ["service:v2alpha:quality-agent"], "verification": []}
        self.assertEqual(runtime.validate_project(project)["identities"], ["service:v2alpha:quality-agent"])
        forbidden = json.loads(json.dumps(project)); forbidden["resources"][0]["manifest"]["type"] = "secret"
        with self.assertRaises(ValueError): runtime.validate_project(forbidden)
        mismatch = json.loads(json.dumps(project)); mismatch["resources"][0]["identifier"] = "service:v2alpha:other"
        with self.assertRaises(ValueError): runtime.validate_project(mismatch)
        bad_path = json.loads(json.dumps(project)); bad_path["files"][0]["path"] = "../escape"
        with self.assertRaises(ValueError): runtime.validate_project(bad_path)

    def test_access_plan_is_deterministic_and_owner_private(self):
        project = {"resources": [{"manifest": {"spec": {"runAsUser": "qualityagent", "compute": "engineering-compute", "http": {"enabled": True, "path": "/quality-agent"}}}}]}
        plan = runtime.derive_access_plan(project, "akshaychametmdcio", "engineering")
        self.assertEqual(plan["applicationId"], "qualityagent")
        serialized = json.dumps(plan)
        self.assertIn("users:id:akshaychametmdcio", serialized)
        self.assertIn("/quality-agent/**", serialized)
        predicates = {value for policy in plan["policies"] for value in policy["predicates"]}
        self.assertTrue({"delete", "update", "create"}.isdisjoint(predicates))

    def test_chat_and_deploy_are_separate_server_routes(self):
        source = (ROOT / "runtime/server.py").read_text()
        self.assertIn('path == "/api/prd/approve"', source)
        self.assertIn('path == "/api/deploy"', source)
        self.assertIn('expected = f"DEPLOY {project[\'project_name\']}"', source)
        self.assertNotIn("dataos_resource_delete", source.split("class BuilderApp", 1)[1])

    def test_official_data_product_builder_journey_is_packaged(self):
        skill = (ROOT / "skills/data-product-builder-routing/SKILL.md").read_text()
        self.assertIn("npx dataproduct-builder-skills@latest", skill)
        self.assertIn("design-data-product", skill)
        self.assertIn("build-data-product", skill)
        self.assertIn("fix-data-product", skill)
        self.assertIn("Python 3.10 or 3.11", skill)

    def test_discovery_is_evidence_only_and_has_no_generic_environments(self):
        discovery = (ROOT / "skills/requirements-discovery/SKILL.md").read_text()
        self.assertNotIn("sandbox, test, or production", discovery)
        self.assertIn("Do not present model knowledge as DataOS knowledge", discovery)
        self.assertIn("Never offer invented multiple-choice options", discovery)
        source = (ROOT / "runtime/server.py").read_text()
        self.assertIn("Do not rely on general model knowledge for DataOS claims", source)
        self.assertIn("Keep unknown platform facts explicitly Unverified", source)

    def test_browser_forwards_valid_dataos_oidc_session(self):
        source = (ROOT / "runtime/app.js").read_text()
        self.assertIn("modern-oidc.user:", source)
        self.assertIn("access_token", source)
        self.assertIn("Authorization: `Bearer ${credential}`", source)
        self.assertIn("credentials: 'same-origin'", source)

    def test_owner_session_is_signed_scoped_and_expires(self):
        config = {"owner": "akshaychametmdcio", "runtime_key": "runtime-secret"}
        token = runtime.owner_session(config)
        self.assertTrue(runtime.valid_owner_session(token, config))
        self.assertFalse(runtime.valid_owner_session(token + "x", config))
        self.assertFalse(runtime.valid_owner_session(token, dict(config, owner="someoneelse")))
        self.assertFalse(runtime.valid_owner_session(runtime.owner_session(config, lifetime=-1), config))
        source = (ROOT / "runtime/server.py").read_text()
        self.assertIn("HttpOnly; Secure; SameSite=Strict", source)
        self.assertIn('path == "/healthz"', source)
        self.assertIn("Path={app.cfg['base_path']}", source)
        settings_route = source.split('if path == "/api/settings/keys":', 1)[1].split("if not self._private()", 1)[0]
        self.assertNotIn("authorize_owner_key", settings_route)

    def test_api_key_owner_is_verified_from_exact_heimdall_token_record(self):
        token = "agentbuilder." + "a" * 64
        config = {"owner": "akshaychametmdcio", "fqdn": "example.dataos.cloud"}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self):
                return json.dumps([{"name": "agentbuilder", "user_id": "akshaychametmdcio", "data": {"apikey": token}}]).encode()

        opener = Mock(return_value=Response())
        self.assertTrue(runtime.authorize_owner_key(token, config, opener))
        request = opener.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer " + token)
        self.assertEqual(request.get_header("Apikey"), token)
        self.assertIn("/users/akshaychametmdcio/tokens", request.full_url)

        class WrongOwner(Response):
            def read(self):
                return json.dumps([{"name": "agentbuilder", "user_id": "someoneelse", "data": {"apikey": token}}]).encode()

        self.assertFalse(runtime.authorize_owner_key(token, config, Mock(return_value=WrongOwner())))


if __name__ == "__main__":
    unittest.main()
