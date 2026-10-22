#!/usr/bin/env python3
"""Authenticated target checks and idempotent policy reconciliation."""
import json
from pathlib import Path
import re
import subprocess


def verify_target(c):
    directory = Path(c['cli_config_directory'])
    checks = [(directory / 'dataos.context.yaml', 'current_context_name', c['context']),
              (directory / c['context'] / '.dataos.tenancy.config.yaml', 'dataos_fqdn', c['host']),
              (directory / c['context'] / '.dataos.tenancy.config.yaml', 'dataos_tenant', c['tenant'])]
    for path, field, expected in checks:
        values = re.findall(r'^\s*' + field + r':\s*(\S+)\s*$', path.read_text(), re.M)
        if [x.strip('\"\'') for x in values] != [expected]:
            raise ValueError('CLI target mismatch: ' + field)


def request(c, path, method='GET', body=None):
    credential = Path(c['cli_config_directory']) / ('.' + c['host'] + '.dataos.cred.config.yaml')
    token = re.search(r'^\s*access_token:\s*(\S+)\s*$', credential.read_text(), re.M)
    if token is None:
        raise ValueError('No operator token in the CLI credential file')
    token = token[1].strip('\"\'')
    lines = ['url = ' + json.dumps('https://' + c['host'] + path),
             'header = ' + json.dumps('Authorization: Bearer ' + token),
             'header = "Content-Type: application/json"', 'request = ' + json.dumps(method)]
    if body is not None:
        lines.append('data = ' + json.dumps(json.dumps(body)))
    result = subprocess.run(['curl', '--silent', '--show-error', '--max-time', '60',
                             '--config', '-', '--write-out', '\n%{http_code}'],
                            input='\n'.join(lines) + '\n', text=True, capture_output=True, timeout=65)
    if result.returncode:
        raise RuntimeError('HTTP transport failed; sensitive diagnostics withheld')
    raw, status = result.stdout.rsplit('\n', 1)
    status = int(status)
    if not raw.strip():
        return status, None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError('DataOS API returned non-JSON content with HTTP ' + str(status)) from exc


def policies(c, directory, apply):
    desired = json.loads((directory / 'access.json').read_text())
    status, actual = request(c, '/heimdall/api/v1/policies')
    if status != 200 or not isinstance(actual, list):
        raise RuntimeError('Cannot read existing policies: HTTP ' + str(status))
    actual = {p['name']: p for p in actual}
    missing = []
    for policy in desired:
        old = actual.get(policy['name'])
        if old is None:
            missing.append(policy)
        elif any(old.get(k) != v for k, v in policy.items()):
            raise ValueError('Existing policy differs; no write attempted: ' + policy['name'])
    print(json.dumps({'policy_create': [p['name'] for p in missing],
                      'policy_unchanged': len(desired) - len(missing), 'apply': apply}))
    if apply:
        for policy in missing:
            status, _ = request(c, '/heimdall/api/v1/policies', 'POST', policy)
            if status != 201:
                raise RuntimeError('Policy creation stopped at ' + policy['name'] + ': HTTP ' + str(status))
