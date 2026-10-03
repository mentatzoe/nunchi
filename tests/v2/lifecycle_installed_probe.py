"""Real package/profile lifecycle exercise; run a tests-only copy, not this checkout.

Arguments: --uv ABS --old-wheel ABS --new-wheel ABS --legacy-source ABS.
The selected Python must be a disposable, stock Hermes environment. Package
changes intentionally affect that environment; HOME/HERMES_HOME must be private.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, *, cwd, env):
    result = subprocess.run([str(v) for v in command], cwd=cwd, env=env,
                            text=True, capture_output=True, timeout=180)
    print('COMMAND', [str(v) for v in command], 'EXIT', result.returncode, flush=True)
    print(result.stdout, result.stderr, flush=True)
    if result.returncode:
        raise AssertionError('subprocess failed')
    return result.stdout


DISCOVER = '''
import json, pathlib, socket
from unittest import mock
external=[]
def deny(*args, **kwargs):
    external.append(True)
    raise AssertionError('network unavailable in lifecycle discovery')
socket.socket.connect=deny
socket.socket.connect_ex=deny
with mock.patch('tools.tirith_security.ensure_installed', return_value=None), mock.patch('agent.model_metadata.fetch_model_metadata',return_value={}):
    import hermes_cli.plugins as p
    manager=p.PluginManager()
    manager.discover_and_load()
    result=manager.list_plugins()
    states=[v for v in result if 'nunchi' in v['name']]
    hooks={name: len(callbacks) for name,callbacks in manager._hooks.items()}
    print(json.dumps({'states':states,'hooks':hooks,'external':external}))
    assert not external
'''


def main():
    parser = argparse.ArgumentParser()
    for name in ('uv', 'old-wheel', 'new-wheel', 'legacy-source'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(os.environ['HOME']).resolve()
    assert root.is_relative_to(Path.cwd().resolve()), 'use a disposable tests-only harness home'
    assert not (Path.cwd() / 'src').exists()
    python = Path(sys.executable).absolute()
    import hermes_cli
    host = Path(hermes_cli.__file__).resolve().parent.parent
    def host_hashes():
        return {str(p.relative_to(host)): sha(p) for p in host.rglob('*')
                if p.is_file() and '.venv' not in p.parts and '__pycache__' not in p.parts
                and not p.name.endswith('.pyc') and '.egg-info' not in str(p)}
    before_host = host_hashes()
    from importlib import metadata
    def records():
        return {d.metadata['Name']: hashlib.sha256((d.read_text('RECORD') or '').encode()).hexdigest()
                for d in metadata.distributions() if d.metadata['Name'] != 'nunchi'}
    before_records = records()
    env = {'PATH': os.defpath, 'HOME': str(root), 'HERMES_HOME': str(root / '.hermes'),
           'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'en_US.UTF-8',
           'UV_CACHE_DIR': str(root / 'uv-cache')}
    home = root / '.hermes'
    home.mkdir()
    sibling = home / 'profiles/unrelated'
    sibling.mkdir(parents=True)
    (sibling / 'config.yaml').write_bytes(b'private: unrelated-sentinel\n')
    (home / 'config.yaml').write_bytes(b'# preserve this\nplugins:\n  enabled: [nunchi-gate]\nmodel: untouched\nnunchi:\n  enabled: false\n')
    original_config = (home / 'config.yaml').read_bytes()
    def install(wheel):
        run([args.uv, 'pip', 'install', '--python', python, '--no-deps', '--reinstall', wheel], cwd=root.parent, env=env)
    install(args.old_wheel)
    run([python, '-I', '-m', 'nunchi.install', 'install', '--only', 'hermes', '--repo-root', args.legacy_source,
         '--hermes-home', home], cwd=root.parent, env=env)
    predecessor = home / 'plugins/nunchi-gate'
    assert predecessor.is_dir()
    # Historical upgrades made sibling backups under discovery roots.
    shutil.copytree(predecessor, home / 'plugins/nunchi-gate.bak.historical')
    (home / 'nunchi-gate.state.json').write_text('{"global":{"enabled":false}}')
    before_legacy = {str(p.relative_to(home)): sha(p) for p in home.rglob('*') if p.is_file()}
    discovery = root.parent / 'discovery.py'
    discovery.write_text(DISCOVER)
    old_result = json.loads(run([python, '-I', discovery], cwd=root.parent, env=env).strip().splitlines()[-1])
    assert any(s['name'] == 'nunchi-gate' and s['enabled'] for s in old_result['states']), old_result
    install(args.new_wheel)
    # Import only the wheel, from this point; do not import tests' src setup.
    run([python, '-I', '-c', 'import nunchi,importlib.metadata as m; print(nunchi.__file__); print([(e.name,e.value) for e in m.entry_points(group="hermes_agent.plugins") if e.name=="nunchi"])'], cwd=root.parent, env=env)
    import nunchi
    assert Path(nunchi.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    from nunchi.integrations.hermes_dashboard_store import default_config_paths
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.v2.test_hermes_dashboard import _document
    paths = default_config_paths('default', hermes_home=home)
    config = _document(home)
    config['state_directory'] = str(paths.state_directory)
    supplied = root / 'supplied.json'
    supplied.write_text(json.dumps(config))
    supplied.chmod(0o600)
    cli = [python, '-I', '-m', 'nunchi.integrations.hermes_lifecycle']
    common = ['--hermes-home', home, '--hermes-python', python]
    envelope = json.loads(run([*cli, 'plan', *common, '--mode', 'activate', '--profile', 'default',
        '--config', supplied, '--config-sha256', sha(supplied), '--wheel-sha256', sha(args.new_wheel),
        '--predecessor-wheel', args.old_wheel], cwd=root.parent, env=env))
    assert 'unrelated-sentinel' not in json.dumps(envelope)
    assert 'global' not in json.dumps(envelope['plan']['operations'])
    planfile = root / 'plan.json'
    planfile.write_text(json.dumps(envelope))
    receipt = json.loads(run([*cli, 'apply', *common, '--plan', planfile,
        '--plan-sha256', envelope['plan_sha256'], '--processes-stopped'], cwd=root.parent, env=env))
    assert not predecessor.exists()
    assert not (home / 'plugins/nunchi-gate.bak.historical').exists()
    assert not (home / 'nunchi-gate.state.json').exists()
    for _ in range(2):
        run([*cli, 'verify', *common, '--transaction', receipt['transaction']], cwd=root.parent, env=env)
    # Successful predecessor rollback is a real profile + package sequence,
    # performed before a running process has made later state edits.
    run([*cli, 'rollback', *common, '--mode', 'restore', '--transaction', receipt['transaction'],
         '--plan-sha256', envelope['plan_sha256'], '--processes-stopped'], cwd=root.parent, env=env)
    for relative, expected in before_legacy.items():
        assert sha(home / relative) == expected, relative
    assert (home / 'config.yaml').read_bytes() == original_config
    retained = home / '.nunchi-lifecycle' / receipt['transaction'] / 'predecessor-package' / args.old_wheel.name
    assert sha(retained) == sha(args.old_wheel)
    install(retained)
    restored = json.loads(run([python, '-I', discovery], cwd=root.parent, env=env).strip().splitlines()[-1])
    assert any(s['name'] == 'nunchi-gate' and s['enabled'] and not s['error'] for s in restored['states'])
    assert not any(s['name'] == 'nunchi' for s in restored['states'])
    install(args.new_wheel)
    envelope = json.loads(run([*cli, 'plan', *common, '--mode', 'activate', '--profile', 'default',
        '--config', supplied, '--config-sha256', sha(supplied), '--wheel-sha256', sha(args.new_wheel),
        '--predecessor-wheel', args.old_wheel], cwd=root.parent, env=env))
    planfile.write_text(json.dumps(envelope))
    receipt = json.loads(run([*cli, 'apply', *common, '--plan', planfile,
        '--plan-sha256', envelope['plan_sha256'], '--processes-stopped'], cwd=root.parent, env=env))
    loaded = json.loads(run([python, '-I', discovery], cwd=root.parent, env=env).strip().splitlines()[-1])
    assert all(s['name'] != 'nunchi-gate' for s in loaded['states'])
    nunchi_state = next(s for s in loaded['states'] if s['name'] == 'nunchi')
    assert nunchi_state['enabled'] and not nunchi_state['error'], loaded
    assert loaded['hooks'] == {'pre_tool_call': 1, 'pre_llm_call': 1, 'post_llm_call': 1}, loaded
    # Ordinary dashboard Save grants attention trust and serializes host config
    # as JSON. The installed CLI must accept those bytes without normalization.
    save_script = root.parent / 'save.py'
    save_script.write_text('''
import json, os, sys
from pathlib import Path
from nunchi.integrations.hermes_dashboard_store import read_dashboard_snapshot, write_config_document
from nunchi.integrations.hermes_attention_trust import attention_trust_status
profile = sys.argv[1]
snapshot = read_dashboard_snapshot(profile, environ=os.environ)
if len(sys.argv) > 2:
    snapshot = write_config_document(profile, document=json.loads(Path(sys.argv[2]).read_bytes()),
                                     expected_revision=snapshot.revision, environ=os.environ)
assert attention_trust_status(Path(os.environ['HERMES_HOME']), snapshot.config)['ready']
print('REAL_SAVE_TRUST_READY')
''')
    run([python, '-I', save_script, 'default', supplied], cwd=root.parent, env=env)
    saved_host = (home / 'config.yaml').read_bytes()
    assert isinstance(json.loads(saved_host), dict)
    saved_trust = json.loads(saved_host)['plugins']['entries']['nunchi']['llm']
    # Fresh process is registration evidence, not a live platform canary.
    retirement = json.loads(run([*cli, 'plan', *common, '--mode', 'retire', '--profile', 'default',
                                 '--wheel-sha256', sha(args.new_wheel)], cwd=root.parent, env=env))
    retirementfile = root / 'retirement.json'
    retirementfile.write_text(json.dumps(retirement))
    retired = json.loads(run([*cli, 'apply', *common, '--plan', retirementfile,
        '--plan-sha256', retirement['plan_sha256'], '--processes-stopped'], cwd=root.parent, env=env))
    run([*cli, 'verify', *common, '--transaction', retired['transaction']], cwd=root.parent, env=env)
    assert json.loads((home / 'config.yaml').read_bytes())['plugins']['entries']['nunchi']['llm'] == saved_trust
    stock = json.loads(run([python, '-I', discovery], cwd=root.parent, env=env).strip().splitlines()[-1])
    assert not any(s['enabled'] for s in stock['states'])
    assert not (home / 'plugins/nunchi-dashboard').exists()
    run([args.uv, 'pip', 'uninstall', '--python', python, 'nunchi'], cwd=root.parent, env=env)
    run([python, '-I', '-c', 'import importlib.util; assert importlib.util.find_spec("nunchi") is None'], cwd=root.parent, env=env)
    install(args.new_wheel)
    run([*cli, 'rollback', *common, '--mode', 'restore', '--transaction', retired['transaction'],
         '--plan-sha256', retirement['plan_sha256'], '--processes-stopped'], cwd=root.parent, env=env)
    assert (home / 'config.yaml').read_bytes() == saved_host
    run([*cli, 'verify', *common, '--transaction', retired['transaction']], cwd=root.parent, env=env)
    run([python, '-I', save_script, 'default'], cwd=root.parent, env=env)
    # Discovery generates owned bytecode/data after activation. The activation
    # rollback must refuse those intervening state changes, not erase them.
    result = subprocess.run([str(v) for v in [*cli, 'rollback', *common, '--mode', 'restore',
        '--transaction', receipt['transaction'], '--plan-sha256', envelope['plan_sha256'], '--processes-stopped']],
        cwd=root.parent, env=env, text=True, capture_output=True)
    print('ACTIVATION_ROLLBACK_AFTER_RUNTIME', result.returncode, result.stdout, result.stderr)
    # If runtime has not changed managed bytes, restoration is exact; otherwise
    # later state is deliberately protected. The separate pristine cycle below
    # exercises the successful predecessor restoration package sequence.
    if result.returncode:
        assert 'later edits' in result.stderr
    assert (sibling / 'config.yaml').read_bytes() == b'private: unrelated-sentinel\n'
    # Exercise the named-profile bridge in a fresh stock process as well: no
    # machine enablement/config rewrite or machine dashboard installation.
    named_user = root / 'named-user'
    machine = named_user / '.hermes'
    named_home = machine / 'profiles/worker'
    named_home.mkdir(parents=True)
    machine_config = b'plugins:\n  disabled: [nunchi]\nprivate: untouched\n'
    (machine / 'config.yaml').write_bytes(machine_config)
    (named_home / 'config.yaml').write_text('plugins:\n  enabled: []\n')
    named_config = _document(named_home)
    named_config['hermes_profile'] = 'worker'
    named_config['state_directory'] = str(default_config_paths('worker', hermes_home=named_home).state_directory)
    supplied.write_text(json.dumps(named_config))
    named_env = dict(env, HOME=str(named_user), HERMES_HOME=str(named_home))
    named_common = ['--hermes-home', named_home, '--hermes-python', python]
    named_plan = json.loads(run([*cli, 'plan', *named_common, '--mode', 'activate', '--profile', 'worker',
        '--config', supplied, '--config-sha256', sha(supplied), '--wheel-sha256', sha(args.new_wheel)],
        cwd=root.parent, env=named_env))
    planfile.write_text(json.dumps(named_plan))
    run([*cli, 'apply', *named_common, '--plan', planfile, '--plan-sha256', named_plan['plan_sha256'],
         '--processes-stopped'], cwd=root.parent, env=named_env)
    run([python, '-I', '-c', 'from nunchi.integrations.hermes_dashboard_install import install_dashboard_for_profile; print(install_dashboard_for_profile(profile="worker"))'],
        cwd=root.parent, env=named_env)
    run([python, '-I', save_script, 'worker', supplied], cwd=root.parent, env=named_env)
    named_saved = (named_home / 'config.yaml').read_bytes()
    named_trust = json.loads(named_saved)['plugins']['entries']['nunchi']['llm']
    def named_apply(mode):
        arguments = ['--config', supplied, '--config-sha256', sha(supplied)] if mode == 'activate' else []
        planned = json.loads(run([*cli, 'plan', *named_common, '--mode', mode, '--profile', 'worker',
            '--wheel-sha256', sha(args.new_wheel), *arguments], cwd=root.parent, env=named_env))
        planfile.write_text(json.dumps(planned))
        applied = json.loads(run([*cli, 'apply', *named_common, '--plan', planfile,
            '--plan-sha256', planned['plan_sha256'], '--processes-stopped'], cwd=root.parent, env=named_env))
        run([*cli, 'verify', *named_common, '--transaction', applied['transaction']], cwd=root.parent, env=named_env)
        assert json.loads((named_home / 'config.yaml').read_bytes())['plugins']['entries']['nunchi']['llm'] == named_trust
        return planned, applied
    named_retirement, named_retired = named_apply('retire')
    run([args.uv, 'pip', 'uninstall', '--python', python, 'nunchi'], cwd=root.parent, env=env)
    run([python, '-I', '-c', 'import importlib.util; assert importlib.util.find_spec("nunchi") is None'], cwd=root.parent, env=env)
    install(args.new_wheel)
    run([*cli, 'rollback', *named_common, '--mode', 'restore', '--transaction', named_retired['transaction'],
         '--plan-sha256', named_retirement['plan_sha256'], '--processes-stopped'], cwd=root.parent, env=named_env)
    assert (named_home / 'config.yaml').read_bytes() == named_saved
    run([*cli, 'verify', *named_common, '--transaction', named_retired['transaction']], cwd=root.parent, env=named_env)
    run([python, '-I', save_script, 'worker'], cwd=root.parent, env=named_env)
    named_apply('retire')
    named_apply('activate')
    run([python, '-I', save_script, 'worker', supplied], cwd=root.parent, env=named_env)
    reactivated = json.loads(run([python, '-I', discovery], cwd=root.parent, env=named_env).strip().splitlines()[-1])
    assert any(s['name'] == 'nunchi' and s['enabled'] and not s['error'] for s in reactivated['states'])
    assert (machine / 'config.yaml').read_bytes() == machine_config
    assert (home / 'config.yaml').read_bytes() == saved_host
    assert (sibling / 'config.yaml').read_bytes() == b'private: unrelated-sentinel\n'
    assert not (machine / 'plugins').exists()
    assert records() == before_records, 'other distributions RECORD changed'
    assert host_hashes() == before_host, 'host sources changed'
    print('LIFECYCLE_PACKAGE_PROFILE_PASS', json.dumps({'python': str(python), 'old_wheel': sha(args.old_wheel),
        'new_wheel': sha(args.new_wheel), 'host_files': len(before_host), 'other_records': len(before_records), 'fresh_registration': True,
        'live_platform': False, 'restoration_after_runtime_refused': bool(result.returncode)}))


if __name__ == '__main__':
    main()
