#!/usr/bin/env python3
"""Render, validate and optionally deploy the private DataOS operations observer."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def load_platform():
    spec = importlib.util.spec_from_file_location('platform_access', ROOT / 'deploy/platform.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configuration(path, cli, config_directory):
    c = json.loads(path.read_text())
    required = set(json.loads((ROOT / 'environment.example.json').read_text()))
    missing = required - set(c)
    if missing:
        raise ValueError('Missing configuration: ' + ', '.join(sorted(missing)))
    for key in ('agent_id',):
        if not re.fullmatch(r'[a-z][a-z0-9]{0,47}', str(c[key])):
            raise ValueError('Invalid resource name: ' + key)
    for key in ('tenant', 'operator_id', 'compute', 'dataplane'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', str(c[key])):
            raise ValueError('Invalid identifier: ' + key)
    if any(char in c['operator_id'] for char in '*?[]'):
        raise ValueError('operator_id must be one exact DataOS user ID; wildcards are forbidden')
    if c['operator_id'].lower() == c['agent_id'].lower():
        raise ValueError('operator_id must be a human user distinct from the application identity')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]+', str(c['host'])):
        raise ValueError('host must be a bare hostname')
    if not isinstance(c['resource_types'], list) or not c['resource_types']:
        raise ValueError('resource_types must be a non-empty list')
    supported_types = {'app', 'bundle', 'compute', 'dataplane', 'depot', 'lakehouse', 'link',
                       'minerva', 'nilus-v5', 'service', 'stack', 'volume', 'vulcan', 'vulcantest',
                       'worker', 'workflow'}
    if any(item not in supported_types for item in c['resource_types']):
        raise ValueError('resource_types may contain only: ' + ', '.join(sorted(supported_types)))
    c['resource_types'] = list(dict.fromkeys(c['resource_types']))
    for key, minimum, maximum in (('poll_interval_seconds', 30, 3600), ('pending_threshold_seconds', 60, 86400)):
        if not isinstance(c[key], int) or not minimum <= c[key] <= maximum:
            raise ValueError(f'{key} must be between {minimum} and {maximum}')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', str(c['model'])):
        raise ValueError('Invalid model name')
    if not shutil.which(cli):
        raise ValueError('DataOS CLI executable not found')
    c['cli'] = cli
    c['cli_config_directory'] = str(Path(config_directory).expanduser().resolve())
    context_file = Path(c['cli_config_directory']) / 'dataos.context.yaml'
    text = context_file.read_text()
    match = re.search(r'^\s*current_context_name:\s*(\S+)\s*$', text, re.M)
    if not match:
        raise ValueError('CLI context is not initialized')
    c['context'] = match[1].strip('\"\'')
    c['resource_types_csv'] = ','.join(c['resource_types'])
    c['state_volume'] = (c['agent_id'] + 'state')[:48]
    return c


def render(c, output):
    values = dict(c, **json.loads((ROOT / 'deploy/runtime.lock.json').read_text()))
    commands = []
    for source in sorted((ROOT / 'runtime').iterdir()):
        if source.is_file() and source.suffix in ('.mjs', '.js', '.html', '.css'):
            destination = '/etc/dataos/work/observer/' + source.name
            payload = base64.b64encode(source.read_bytes()).decode()
            commands.append("printf '%s' '" + payload + "' | base64 -d > " + destination)
    skill_root = ROOT / 'skills' / 'dataos-cli-diagnostics'
    for source in sorted(path for path in skill_root.rglob('*') if path.is_file() and path.suffix in ('.md', '.yaml')):
        relative = source.relative_to(skill_root)
        destination = '/etc/dataos/work/observer/skills/dataos-cli-diagnostics/' + relative.as_posix()
        payload = base64.b64encode(source.read_bytes()).decode()
        commands.append("mkdir -p " + str(Path(destination).parent))
        commands.append("printf '%s' '" + payload + "' | base64 -d > " + destination)
    values['RUNTIME_FILES'] = '\n'.join(commands)
    # DataOS may keep a stateful Service container alive when only its inline
    # bootstrap script changes. Put the content hash in the Service spec so a
    # real code change deterministically triggers a rolling restart.
    values['build_id'] = hashlib.sha256(values['RUNTIME_FILES'].encode()).hexdigest()[:12]

    def replace(text):
        def token(match):
            key = match[1]
            if key not in values:
                raise ValueError('Unresolved template variable: ' + key)
            return str(values[key])
        return re.sub(r'@@([^@]+)@@', token, text)

    def walk(obj):
        if isinstance(obj, str):
            return replace(obj)
        if isinstance(obj, list):
            return [walk(item) for item in obj]
        if isinstance(obj, dict):
            return {key: walk(value) for key, value in obj.items()}
        return obj

    service = walk(json.loads((ROOT / 'deploy/service.template.json').read_text()))
    link = walk(json.loads((ROOT / 'deploy/link.template.json').read_text()))
    volume = walk(json.loads((ROOT / 'deploy/volume.template.json').read_text()))
    policies = walk(json.loads((ROOT / 'deploy/access.template.json').read_text()))
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [('service.json', service), ('link.json', link), ('volume.json', volume),
                        ('access.json', policies), ('config.json', c)]:
        (output / name).write_text(json.dumps(value, indent=2) + '\n')
    return service, link, policies


def cli_run(c, args):
    result = subprocess.run([c['cli'], *args], capture_output=True, text=True, timeout=120,
                            env=dict(os.environ, DATAOS_CONFIG_DIRECTORY=c['cli_config_directory']))
    if result.returncode or 'level=error' in (result.stdout + result.stderr).lower():
        raise RuntimeError('CLI operation failed: ' + ' '.join(args[:3]) + '; inspect with your operator CLI')
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--cli', default='dataos-ctl')
    parser.add_argument('--cli-config', default=os.environ.get('DATAOS_CONFIG_DIRECTORY', str(Path.home() / '.dataos/v2')))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--render-only', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.render_only and args.apply:
        raise ValueError('--render-only and --apply are mutually exclusive')
    c = configuration(args.config, args.cli, args.cli_config)
    platform = load_platform()
    platform.verify_target(c)
    output = args.output or Path(tempfile.mkdtemp(prefix='dataos-observer-')) / 'rendered'
    render(c, output)
    if args.render_only:
        print(json.dumps({'rendered': str(output), 'platform_writes': False}))
        return
    status, user = platform.request(c, '/heimdall/api/v1/users/' + c['agent_id'])
    if status not in (200, 404):
        raise RuntimeError('Cannot inspect application identity: HTTP ' + str(status))
    if status == 200 and (not isinstance(user, dict) or user.get('type') != 'application'):
        raise ValueError('Existing identity is not an application; refusing to reuse it')
    platform.policies(c, output, False)
    print(json.dumps({'identity': 'exists' if status == 200 else 'create', 'rendered': str(output)}))
    if not args.apply:
        return
    if status == 404:
        cli_run(c, ['user', 'create', '--user_id', c['agent_id'], '--name', c['agent_id'], '--type', 'application'])
    found = cli_run(c, ['resource', 'get', '-t', 'compute', '-n', c['compute'], '-a', '-d'])
    if c['compute'] not in found:
        raise ValueError('Configured compute not found: ' + c['compute'])
    platform.policies(c, output, True)
    cli_run(c, ['resource', 'apply', '-f', str(output / 'volume.json'), '--lint', '--disable-interpolation'])
    cli_run(c, ['resource', 'apply', '-f', str(output / 'service.json'), '--lint', '--disable-interpolation'])
    cli_run(c, ['resource', 'apply', '-f', str(output / 'link.json'), '--lint', '--disable-interpolation'])
    cli_run(c, ['resource', 'apply', '-f', str(output / 'volume.json'), '--disable-interpolation'])
    cli_run(c, ['resource', 'apply', '-f', str(output / 'service.json'), '--disable-interpolation'])
    cli_run(c, ['resource', 'apply', '-f', str(output / 'link.json'), '--disable-interpolation'])
    print(json.dumps({'service': 'service:v2alpha:' + c['agent_id'],
                      'data_app': 'link:v1alpha:' + c['agent_id'] + '-ui', 'state': 'submitted',
                      'verify': 'Inspect runtime/logs, open the private dashboard, and confirm a successful first scan.'}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Installer failed; sensitive diagnostics withheld', file=sys.stderr)
        sys.exit(1)
