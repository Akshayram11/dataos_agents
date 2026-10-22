"""Offline deployment and least-privilege checks; no network or model calls."""
import base64
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('observer_installer', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PackageChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.area = Path(self.tmp.name)
        self.config = json.loads((ROOT / 'environment.example.json').read_text())
        self.path = self.area / 'environment.json'
        self.path.write_text(json.dumps(self.config))
        self.cli_dir = self.area / 'cli'
        (self.cli_dir / 'sawan-rn').mkdir(parents=True)
        (self.cli_dir / 'dataos.context.yaml').write_text('contexts:\n  current_context_name: sawan-rn\n')
        (self.cli_dir / 'sawan-rn/.dataos.tenancy.config.yaml').write_text(
            'tenancy:\n  dataos_fqdn: sawaniks-081726.instance.dataos.cloud\n  dataos_tenant: engineering\n')

    def load(self):
        return installer.configuration(self.path, '/usr/bin/true', str(self.cli_dir))

    def test_render_is_private_stateful_and_contains_runtime(self):
        service, link, policies = installer.render(self.load(), self.area / 'rendered')
        self.assertEqual(service['spec']['runAsUser'], 'dataosopsagent')
        self.assertTrue(service['spec']['stateful'])
        self.assertEqual(service['spec']['volumes'], [{'id': 'dataosopsagentstate', 'directory': '/etc/dataos/persist'}])
        volume = json.loads((self.area / 'rendered' / 'volume.json').read_text())
        self.assertEqual(volume['spec'], {'dataplane': 'sawandp01', 'size': '1Gi', 'type': 'disk'})
        self.assertNotIn('disk', service['spec'])
        # Browser navigation cannot attach a bearer header. The public ingress only
        # serves the inert app shell; server-side Heimdall auth protects every API.
        self.assertTrue(service['spec']['http']['noNetworkAuthorization'])
        self.assertEqual(link['type'], 'link')
        self.assertEqual(link['owner'], 'akshaychametmdcio')
        self.assertEqual(link['spec']['link']['owners'], ['akshaychametmdcio'])
        self.assertEqual(link['spec']['link']['url'],
                         'https://sawaniks-081726.instance.dataos.cloud/dataosopsagent/')
        boot = service['spec']['stackSpec']['arguments'][0]
        self.assertIn("export OBSERVER_OWNER_ID='akshaychametmdcio'", boot)
        payloads = [base64.b64decode(value).decode() for value in
                    re.findall(r"printf '%s' '([A-Za-z0-9+/=]+)' \| base64 -d", boot)]
        self.assertTrue(any('createObserver' in text for text in payloads))
        self.assertTrue(any('Operations Observer' in text for text in payloads))
        self.assertTrue(any('From signal to action' in text for text in payloads))
        self.assertTrue(any('name: dataos-cli-diagnostics' in text for text in payloads))
        serialized = json.dumps([service, policies]).lower()
        self.assertNotIn('@@', serialized)
        script = self.area / 'bootstrap.sh'
        script.write_text(boot)
        subprocess.run(['bash', '-n', str(script)], check=True)

    def test_application_identity_has_no_mutation_permissions(self):
        _, _, policies = installer.render(self.load(), self.area / 'rendered')
        application = [policy for policy in policies
                       if f"users:id:{self.config['agent_id']}" in policy['subjects']['tags']]
        predicates = {predicate for policy in application for predicate in policy['predicates']}
        self.assertTrue({'read', 'read_log', 'get', 'use'} <= predicates)
        self.assertFalse({'post', 'put', 'delete', 'create', 'update', 'create_in', 'update_in', 'delete_in'} & predicates)
        self.assertNotIn('secret', json.dumps(application).lower())

    def test_dashboard_owner_is_exact_and_distinct(self):
        for invalid in ('*', 'akshay*', 'akshay?', 'akshay[0-9]', 'dataosopsagent'):
            self.config['operator_id'] = invalid
            self.path.write_text(json.dumps(self.config))
            with self.subTest(operator_id=invalid), self.assertRaises(ValueError):
                self.load()

    def test_polling_boundaries_and_resource_types_are_validated(self):
        for key, value in [('poll_interval_seconds', 5), ('pending_threshold_seconds', 30)]:
            changed = dict(self.config, **{key: value})
            self.path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                self.load()
        for invalid_types in (['service', '../secret'], ['secret']):
            self.path.write_text(json.dumps(dict(self.config, resource_types=invalid_types)))
            with self.subTest(resource_types=invalid_types), self.assertRaises(ValueError):
                self.load()

    def test_resource_api_policy_is_limited_to_monitored_types(self):
        _, _, policies = installer.render(self.load(), self.area / 'rendered')
        api = next(policy for policy in policies if policy['name'].endswith('-resource-api-read'))
        paths = api['objects']['paths']
        self.assertTrue(paths)
        self.assertFalse(any(path.endswith('/resources/**') for path in paths))
        self.assertFalse(any('/secret' in path for path in paths))

    def test_target_mismatch_fails_closed(self):
        platform = installer.load_platform()
        config = self.load()
        platform.verify_target(config)
        with self.assertRaises(ValueError):
            platform.verify_target(dict(config, tenant='wrong'))

    def test_existing_render_directory_is_preserved(self):
        output = self.area / 'rendered'
        output.mkdir()
        sentinel = output / 'keep'
        sentinel.write_text('preserve')
        with self.assertRaises(FileExistsError):
            installer.render(self.load(), output)
        self.assertEqual(sentinel.read_text(), 'preserve')

    def test_policy_conflict_prevents_mutation(self):
        platform = installer.load_platform()
        output = self.area / 'rendered'
        config = self.load()
        _, _, policies = installer.render(config, output)
        conflict = dict(policies[-1], allow=False)
        calls = []

        def request(_config, _path, method='GET', body=None):
            calls.append(method)
            return 200, [conflict]

        platform.request = request
        with self.assertRaises(ValueError):
            platform.policies(config, output, True)
        self.assertEqual(calls, ['GET'])


if __name__ == '__main__':
    unittest.main()
