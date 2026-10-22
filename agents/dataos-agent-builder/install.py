#!/usr/bin/env python3
"""Render, validate, and optionally deploy the private DataOS Agent Builder."""
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
    config = json.loads(path.read_text())
    required = set(json.loads((ROOT / 'environment.example.json').read_text()))
    missing = required - set(config)
    if missing:
        raise ValueError('Missing configuration: ' + ', '.join(sorted(missing)))
    if not re.fullmatch(r'[a-z][a-z0-9]{0,47}', str(config['agent_id'])):
        raise ValueError('Invalid agent_id')
    for key in ('tenant', 'operator_id', 'compute', 'dataplane'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', str(config[key])):
            raise ValueError('Invalid identifier: ' + key)
    if any(char in config['operator_id'] for char in '*?[]'):
        raise ValueError('operator_id must be one exact DataOS user ID; wildcards are forbidden')
    if config['operator_id'].lower() == config['agent_id'].lower():
        raise ValueError('operator_id must be distinct from the application identity')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]+', str(config['host'])):
        raise ValueError('host must be a bare hostname')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', str(config['model'])):
        raise ValueError('Invalid model name')
    if not shutil.which(cli):
        raise ValueError('DataOS CLI executable not found')
    config['cli'] = cli
    config['cli_config_directory'] = str(Path(config_directory).expanduser().resolve())
    context_file = Path(config['cli_config_directory']) / 'dataos.context.yaml'
    match = re.search(r'^\s*current_context_name:\s*(\S+)\s*$', context_file.read_text(), re.M)
    if not match:
        raise ValueError('CLI context is not initialized')
    config['context'] = match[1].strip('\"\'')
    return config


def render(config, output):
    values = dict(config, **json.loads((ROOT / 'deploy/runtime.lock.json').read_text()))
    commands = []
    runtime_sources = sorted((ROOT / 'runtime').iterdir())
    skill_sources = sorted((ROOT / 'skills').glob('*/SKILL.md'))
    for source in [*runtime_sources, *skill_sources]:
        if (source.is_file() and source.suffix in ('.py', '.js', '.html', '.css')
                and not source.name.startswith('test_')) or source.name == 'SKILL.md':
            if source.name == 'SKILL.md':
                destination = f'/etc/dataos/work/agent-builder/skills/{source.parent.name}/SKILL.md'
            else:
                destination = '/etc/dataos/work/agent-builder/' + source.name
            payload = base64.b64encode(source.read_bytes()).decode()
            commands.append('mkdir -p ' + str(Path(destination).parent))
            commands.append("printf '%s' '" + payload + "' | base64 -d > " + destination)
    values['RUNTIME_FILES'] = '\n'.join(commands)
    values['build_id'] = hashlib.sha256(values['RUNTIME_FILES'].encode()).hexdigest()[:12]

    def replace(text):
        def token(match):
            key = match[1]
            if key not in values:
                raise ValueError('Unresolved template variable: ' + key)
            return str(values[key])
        return re.sub(r'@@([^@]+)@@', token, text)

    def walk(value):
        if isinstance(value, str):
            return replace(value)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value

    service = walk(json.loads((ROOT / 'deploy/service.template.json').read_text()))
    link = walk(json.loads((ROOT / 'deploy/link.template.json').read_text()))
    policies = walk(json.loads((ROOT / 'deploy/access.template.json').read_text()))
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [('service.json', service), ('link.json', link),
                        ('access.json', policies), ('config.json', config)]:
        (output / name).write_text(json.dumps(value, indent=2) + '\n')
    return service, link, policies


def cli_run(config, args):
    result = subprocess.run([config['cli'], *args], capture_output=True, text=True, timeout=120,
                            env=dict(os.environ, DATAOS_CONFIG_DIRECTORY=config['cli_config_directory']))
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
    config = configuration(args.config, args.cli, args.cli_config)
    platform = load_platform()
    platform.verify_target(config)
    output = args.output or Path(tempfile.mkdtemp(prefix='dataos-agent-builder-')) / 'rendered'
    render(config, output)
    if args.render_only:
        print(json.dumps({'rendered': str(output), 'platform_writes': False}))
        return
    status, user = platform.request(config, '/heimdall/api/v1/users/' + config['agent_id'])
    if status not in (200, 404):
        raise RuntimeError('Cannot inspect application identity: HTTP ' + str(status))
    if status == 200 and (not isinstance(user, dict) or user.get('type') != 'application'):
        raise ValueError('Existing identity is not an application; refusing to reuse it')
    platform.policies(config, output, False)
    print(json.dumps({'identity': 'exists' if status == 200 else 'create', 'rendered': str(output)}))
    if not args.apply:
        return
    if status == 404:
        cli_run(config, ['user', 'create', '--user_id', config['agent_id'], '--name', config['agent_id'], '--type', 'application'])
    found = cli_run(config, ['resource', 'get', '-t', 'compute', '-n', config['compute'], '-a', '-d'])
    if config['compute'] not in found:
        raise ValueError('Configured compute not found: ' + config['compute'])
    platform.policies(config, output, True)
    for name in ('service.json', 'link.json'):
        cli_run(config, ['resource', 'apply', '-f', str(output / name), '--lint', '--disable-interpolation'])
    for name in ('service.json', 'link.json'):
        cli_run(config, ['resource', 'apply', '-f', str(output / name), '--disable-interpolation'])
    print(json.dumps({'service': 'service:v2alpha:' + config['agent_id'],
                      'data_app': 'link:v1alpha:' + config['agent_id'] + '-ui', 'state': 'submitted'}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Installer failed; sensitive diagnostics withheld', file=sys.stderr)
        sys.exit(1)
