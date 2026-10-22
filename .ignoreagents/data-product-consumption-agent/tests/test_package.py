"""Offline deployment and least-privilege checks."""
import base64
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('consumption_installer', ROOT / 'install.py')
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
        (self.cli_dir / 'dataos.context.yaml').write_text('current_context_name: sawan-rn\n')
        (self.cli_dir / 'sawan-rn/.dataos.tenancy.config.yaml').write_text(
            'dataos_fqdn: sawaniks-081726.instance.dataos.cloud\ndataos_tenant: engineering\n')

    def load(self):
        return installer.configuration(self.path, '/usr/bin/true', str(self.cli_dir))

    def test_render_is_private_stateful_and_mcp_only(self):
        service, link, policies = installer.render(self.load(), self.area / 'rendered')
        self.assertEqual(service['spec']['runAsUser'], 'dataproductagent')
        self.assertNotIn('volumes', service['spec'])
        self.assertNotIn('volumes', service['spec']['use'])
        self.assertEqual(service['spec']['disk'], {
            'size': '1Gi', 'type': 'disk', 'mountPath': '/etc/dataos/persist',
        })
        self.assertEqual(service['spec']['envs']['ARGUSS_MCP_URL'],
                         'https://sawaniks-081726.instance.dataos.cloud/arguss/mcp/')
        self.assertEqual(service['spec']['envs']['AGENT_DATAOS_FQDN'],
                         'sawaniks-081726.instance.dataos.cloud')
        self.assertEqual(link['owner'], 'akshaychametmdcio')
        self.assertEqual(link['spec']['link']['owners'], ['akshaychametmdcio'])
        boot = service['spec']['stackSpec']['arguments'][0]
        payloads = [base64.b64decode(value).decode() for value in
                    re.findall(r"printf '%s' '([A-Za-z0-9+/=]+)' \| base64 -d", boot)]
        runtime = '\n'.join(payloads)
        self.assertIn('createConsumptionAgent', runtime)
        self.assertIn('What would you like to know?', runtime)
        self.assertIn('renderMarkdown', runtime)
        self.assertIn('data-product-consumption', runtime)
        self.assertIn('Quality across products', runtime)
        self.assertNotIn('innerHTML', runtime)
        self.assertNotIn('scrollIntoView', runtime)
        self.assertNotIn('/poros/api/', runtime)
        self.assertNotIn('dataos-ctl', runtime)
        self.assertNotIn('@@', json.dumps([service, link, policies]))
        script = self.area / 'bootstrap.sh'
        script.write_text(boot)
        subprocess.run(['bash', '-n', str(script)], check=True)

    def test_application_identity_has_no_data_or_mutation_permissions(self):
        _, _, policies = installer.render(self.load(), self.area / 'rendered')
        application = [policy for policy in policies
                       if f"users:id:{self.config['agent_id']}" in policy['subjects']['tags']]
        serialized = json.dumps(application).lower()
        self.assertNotIn('/poros/', serialized)
        self.assertNotIn('dataos:resource:vulcan', serialized)
        self.assertNotIn('dataos:resource:volume', serialized)
        predicates = {item for policy in application for item in policy['predicates']}
        self.assertEqual(predicates, {'read', 'use'})
        self.assertFalse({'get', 'post', 'put', 'delete', 'create', 'update'} & predicates)

    def test_owner_and_endpoint_are_exact(self):
        for invalid in ('*', 'akshay*', 'akshay?', 'dataproductagent'):
            self.path.write_text(json.dumps(dict(self.config, operator_id=invalid)))
            with self.subTest(operator_id=invalid), self.assertRaises(ValueError):
                self.load()
        self.path.write_text(json.dumps(dict(self.config, mcp_url='https://evil.example/mcp/')))
        with self.assertRaises(ValueError):
            self.load()

    def test_target_mismatch_fails_closed(self):
        platform = installer.load_platform()
        config = self.load()
        platform.verify_target(config)
        with self.assertRaises(ValueError):
            platform.verify_target(dict(config, tenant='wrong'))


if __name__ == '__main__':
    unittest.main()
