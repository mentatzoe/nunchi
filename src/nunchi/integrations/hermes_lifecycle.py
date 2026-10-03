"""Stopped, profile-local Hermes lifecycle. Never installs packages or restarts hosts.

Transaction data is private and outside discovery roots. All target access uses
no-follow directory descriptors. Receipts contain hashes, not configuration or
state values. A retained before-image is restored only over a recognised
transaction state, including an interrupted rename.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid


class LifecycleError(RuntimeError):
    """Unsafe, drifted or incomplete lifecycle operation."""


STORE = '.nunchi-lifecycle'
_FLAGS = os.O_RDONLY | os.O_NOFOLLOW
_DIR = _FLAGS | os.O_DIRECTORY

# Git blob identities from the historical V1 tree dd03add96128d2658deff2201d7a566722cd5603.
# Only identities ship; no executable V1 compatibility implementation ships.
_V1_BLOBS = {
    '__init__.py': '07d43d5ca84b72c1486c0d7a10baec0b3ef094ae',
    'dashboard/index.js': '737e87ab0f8d01b2ecf0aaeb269168dc8436ec93',
    'dashboard/manifest.json': '5517a3c04e5cdc0e625af637d92cdde572a0ed0b',
    'dashboard/plugin_api.py': '84dd63637b2b437d12d066d4adff6f13bed90d56',
    'plugin.yaml': 'bdc4989be72b17100bfcfc529ff81f40acf499c2',
    'resolve.py': '1c643533bf99f76a03cda99ec6859c127846b91f',
    'state.py': '4289ca36a56058a11bad307bf5b5820fa5bb4e09',
}


def _files(tree, prefix=''):
    for name, node in tree['entries'].items():
        path = prefix + name
        if node['type'] == 'directory':
            yield from _files(node, path + '/')
        else:
            yield path


def _legacy_owned(fd, path, tree):
    names = set(_files(tree))
    allowed = set(_V1_BLOBS) | {'.nunchi-install.json'}
    extras = names - allowed
    if any(not re.fullmatch(r'(?:dashboard/)?__pycache__/[A-Za-z_]+\.[A-Za-z0-9-]+\.pyc', n) for n in extras):
        return False
    if not allowed <= names:
        return False
    marker = json.loads(_read(fd, path + '/.nunchi-install.json'))
    if (marker.get('installer'), marker.get('artifact'), marker.get('marker_version')) != ('nunchi-install', 'hermes-plugin', 1):
        return False
    if set(marker.get('files', [])) != set(_V1_BLOBS):
        return False
    for name, expected in _V1_BLOBS.items():
        data = _read(fd, path + '/' + name)
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != expected:
            return False
    return True


def _predecessors(fd, tree, prefix='plugins'):
    import yaml
    for name, entry in tree['entries'].items():
        path = prefix + '/' + name
        if entry['type'] != 'directory':
            continue
        manifest = entry['entries'].get('plugin.yaml')
        if manifest:
            value = yaml.safe_load(_read(fd, path + '/plugin.yaml'))
            if isinstance(value, dict) and value.get('name') in ('nunchi-gate', 'nunchi', 'nunchi-v2'):
                if not _legacy_owned(fd, path, entry):
                    raise LifecycleError('unattributed predecessor runtime')
                yield path
                continue
        if 'nunchi' in name.lower() and name not in ('nunchi-dashboard', 'nunchi-v2-dashboard'):
            raise LifecycleError('unknown Nunchi plugin directory')
        yield from _predecessors(fd, entry, path)



def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _identity(st):
    return [st.st_dev, st.st_ino]


def _parts(path):
    parts = path.split('/')
    if not parts or any(p in ('', '.', '..') for p in parts):
        raise LifecycleError('invalid relative lifecycle path')
    return parts


@contextmanager
def _parent(fd, path):
    parts = _parts(path)
    current = os.dup(fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, _DIR, dir_fd=current)
            os.close(current)
            current = child
        yield current, parts[-1]
    finally:
        os.close(current)


def _read(fd, path):
    with _parent(fd, path) as (parent, name):
        handle = os.open(name, _FLAGS, dir_fd=parent)
        try:
            before = os.fstat(handle)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise LifecycleError('regular unlinked-alias-free file required')
            with os.fdopen(os.dup(handle), 'rb') as stream:
                data = stream.read()
            after = os.fstat(handle)
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ):
                raise LifecycleError('file changed during capture')
            return data
        finally:
            os.close(handle)


def _snapshot(fd, path):
    try:
        with _parent(fd, path) as (parent, name):
            st = os.stat(name, dir_fd=parent, follow_symlinks=False)
            mode = stat.S_IMODE(st.st_mode)
            if stat.S_ISREG(st.st_mode):
                return {'type': 'file', 'mode': mode, 'mtime_ns': st.st_mtime_ns,
                        'sha256': _hash(_read(parent, name))}
            if not stat.S_ISDIR(st.st_mode):
                raise LifecycleError('symlinks and special entries are not managed')
            child = os.open(name, _DIR, dir_fd=parent)
            try:
                return {'type': 'directory', 'mode': mode,
                        'entries': {n: _snapshot(child, n) for n in sorted(os.listdir(child))}}
            finally:
                os.close(child)
    except FileNotFoundError:
        return None


def _write(fd, name, data):
    """Atomic private file replacement; callers must own and pin fd."""
    temp = '.' + uuid.uuid4().hex
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temp, dir_fd=fd)
        except FileNotFoundError:
            pass


def _json_write(fd, name, value):
    _write(fd, name, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())


class _Home:
    def __init__(self, home):
        self.selected = Path(home).expanduser().absolute()
        self.path = self.selected.resolve(strict=True)
        self.fd = os.open(self.path, _DIR)
        self.identity = _identity(os.fstat(self.fd))
        self.bindings = {}

    def check(self):
        if self.selected.resolve(strict=True) != self.path or _identity(self.path.stat()) != self.identity:
            raise LifecycleError('selected home binding changed')
        for path, identity in self.bindings.items():
            with _parent(self.fd, path) as (parent, name):
                st = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISDIR(st.st_mode) or _identity(st) != identity:
                    raise LifecycleError('descendant directory binding changed')

    def close(self):
        os.close(self.fd)


@contextmanager
def _home(home):
    root = _Home(home)
    try:
        yield root
    finally:
        root.close()


@contextmanager
def _locked(root):
    root.check()
    try:
        os.mkdir(STORE, 0o700, dir_fd=root.fd)
    except FileExistsError:
        pass
    store = os.open(STORE, _DIR, dir_fd=root.fd)
    root.bindings[STORE] = _identity(os.fstat(store))
    lock = None
    try:
        if stat.S_IMODE(os.fstat(store).st_mode) != 0o700:
            raise LifecycleError('transaction store must be private (0700)')
        lock = os.open('lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=store)
        if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink != 1:
            raise LifecycleError('invalid lifecycle lock')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LifecycleError('another lifecycle operation owns this home') from exc
        yield store
    finally:
        if lock is not None:
            os.close(lock)
        os.close(store)


def _config(raw, mode):
    # Hermes ships PyYAML. Only splice the plugins node; private host config,
    # comments and trust outside that node retain their exact original bytes.
    import yaml
    text = raw.decode('utf-8')
    try:
        tokens = list(yaml.scan(text))
        if any(isinstance(t, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for t in tokens):
            raise LifecycleError('aliased host configuration needs operator repair')
        node = yaml.compose(text)
        document = yaml.safe_load(text) or {}
        if isinstance(node, yaml.ScalarNode) and node.tag == 'tag:yaml.org,2002:null' and node.value == '':
            node = None  # an empty document with optional explicit markers
        if not isinstance(document, dict) or (node and not isinstance(node, yaml.MappingNode)):
            raise LifecycleError('host config must be a mapping')
        if node and node.flow_style:
            raise LifecycleError('host config must use block YAML')
        keys = [k.value for k, v in node.value] if node else []
        if len(set(keys)) != len(keys):
            raise LifecycleError('duplicate host config keys')
        plugins = document.get('plugins', {})
        if not isinstance(plugins, dict):
            raise LifecycleError('plugins must be a mapping')
        for key in ('enabled', 'disabled'):
            if key in plugins and (not isinstance(plugins[key], list) or
                                   any(not isinstance(v, str) for v in plugins[key])):
                raise LifecycleError('plugin activation lists must contain strings')
        owned = {'nunchi', 'nunchi-gate'}
        plugins['enabled'] = [v for v in plugins.get('enabled', []) if v not in owned]
        plugins['disabled'] = [v for v in plugins.get('disabled', []) if v not in owned]
        plugins['disabled'] += ['nunchi-gate']
        if mode == 'activate':
            plugins['enabled'] += ['nunchi']
        else:
            plugins['disabled'] += ['nunchi']
        replacement = yaml.safe_dump({'plugins': plugins}, sort_keys=False)
        # Insert inside the document, never after an explicit end marker.
        end = next((t.start_mark.index for t in tokens if isinstance(t, yaml.tokens.DocumentEndToken)), len(text))
        rendered = text[:end] + ('\n' if end and text[end - 1] != '\n' else '') + replacement + text[end:]
        if node:
            for key, value in node.value:
                if key.value == 'plugins':
                    if value.flow_style:
                        raise LifecycleError('plugins mapping must use block YAML')
                    # compose's block end mark includes following comments.
                    # End at the last real token's line, retaining those bytes.
                    last = max(t.end_mark.index for t in tokens
                               if key.start_mark.index <= t.start_mark.index < value.end_mark.index
                               and t.end_mark.index <= value.end_mark.index
                               and not isinstance(t, (yaml.tokens.BlockEndToken, yaml.tokens.StreamEndToken)))
                    newline = text.find('\n', last)
                    stop = last if last and text[last - 1] == '\n' else (len(text) if newline == -1 else newline + 1)
                    rendered = text[:key.start_mark.index] + replacement + text[stop:]
                    break
        # Parsing the source is not proof that the splice is valid. Refuse any
        # unsupported layout before staging, including changes to non-owned data.
        document['plugins'] = plugins
        if yaml.safe_load(rendered) != document:
            raise LifecycleError('host YAML layout cannot be preserved safely')
        return rendered.encode()
    except (yaml.YAMLError, UnicodeError) as exc:
        raise LifecycleError('invalid host YAML; values omitted') from exc


def _external(path):
    path = Path(path).absolute()
    if path.is_symlink():
        raise LifecycleError('supplied file must not be a symlink')
    path = path.resolve(strict=True)
    fd = os.open('/', _DIR)
    try:
        return _read(fd, str(path).lstrip('/'))
    finally:
        os.close(fd)


def _payload_hash(payload):
    if payload is None:
        return None
    if isinstance(payload, bytes):
        return _hash(payload)
    return digest({name: _hash(data) for name, data in payload.items()})


def _package():
    """Separate wheel provenance from version and from active-process adoption."""
    import base64
    from importlib import metadata
    import nunchi
    package_root = Path(nunchi.__file__).resolve().parent
    tree = {str(p.relative_to(package_root)): _hash(p.read_bytes())
            for p in package_root.rglob('*.py')}
    result = {'interpreter': str(Path(sys.executable).absolute()),
              'prefix': sys.prefix, 'source_tree_sha256': digest(tree),
              'installed_wheel': False, 'wheel_sha256': None}
    try:
        dist = metadata.distribution('nunchi')
    except metadata.PackageNotFoundError:
        return result
    if Path(str(dist.locate_file('nunchi'))).resolve() != package_root:
        return result
    record = dist.read_text('RECORD')
    if not record:
        return result
    for file in dist.files or []:
        if file.hash is not None:
            raw = Path(str(dist.locate_file(file))).read_bytes()
            observed = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
            if file.hash.mode != 'sha256' or observed != file.hash.value:
                raise LifecycleError('installed package differs from RECORD')
    direct = json.loads(dist.read_text('direct_url.json') or '{}')
    archive = direct.get('archive_info', {})
    wheel_hash = archive.get('hashes', {}).get('sha256')
    if wheel_hash is None and archive.get('hash', '').startswith('sha256='):
        wheel_hash = archive['hash'][7:]
    # uv local-wheel installs intentionally omit archive_info hashes. Bind to
    # the retained local wheel and compare its actual members to installed bytes
    # rather than guessing provenance from an adjacent checkout or version.
    from urllib.parse import urlsplit, unquote
    import io
    import zipfile
    source = urlsplit(direct.get('url', ''))
    if source.scheme == 'file' and not source.netloc and source.path.endswith('.whl'):
        wheel_bytes = _external(Path(unquote(source.path)))
        with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
            for member in wheel.infolist():
                if member.is_dir() or member.filename.endswith('/RECORD'):
                    continue
                if member.filename.startswith('/') or '..' in Path(member.filename).parts or '.data/' in member.filename:
                    raise LifecycleError('unsupported wheel layout')
                installed = Path(str(dist.locate_file(member.filename)))
                if installed.read_bytes() != wheel.read(member):
                    raise LifecycleError('retained wheel differs from installed package')
        observed_wheel = _hash(wheel_bytes)
        if wheel_hash is not None and observed_wheel != wheel_hash:
            raise LifecycleError('retained wheel digest mismatch')
        wheel_hash = observed_wheel
    result.update(distribution='nunchi', version=dist.version,
                  record_sha256=_hash(record.encode()), wheel_sha256=wheel_hash,
                  installed_wheel=bool(wheel_hash and not direct.get('dir_info')))
    return result


def _wheel_identity(path):
    import io
    import zipfile
    from email.parser import BytesParser
    raw = _external(path)
    with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
        names = [n for n in wheel.namelist() if n.endswith('.dist-info/METADATA')]
        if len(names) != 1:
            raise LifecycleError('invalid predecessor wheel')
        metadata = BytesParser().parsebytes(wheel.read(names[0]))
        if metadata['Name'] != 'nunchi':
            raise LifecycleError('predecessor is not a Nunchi wheel')
        return {'sha256': _hash(raw), 'distribution': 'nunchi', 'version': metadata['Version']}


def _build(root, mode, profile, config=None, config_sha256=None, predecessor_wheel=None):
    from nunchi.integrations.hermes_dashboard_install import _assets, _bridge_is_owned
    from nunchi.integrations.hermes_dashboard_store import default_config_paths
    from nunchi.integrations.hermes_v2 import load_pinned_config
    if mode not in ('retire', 'activate'):
        raise LifecycleError('unknown lifecycle mode')
    names = set(os.environ)
    env_snapshot = _snapshot(root.fd, '.env')
    if env_snapshot is not None:
        names.update(re.findall(rb'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=',
                                _read(root.fd, '.env'), re.MULTILINE))
    names = {n.decode() if isinstance(n, bytes) else n for n in names}
    if any(n.startswith('NUNCHI_HERMES_V2_CONFIG') for n in names):
        raise LifecycleError('runtime config overrides exist; reconcile them before using the profile-local lifecycle')
    if 'HERMES_ENABLE_PROJECT_PLUGINS' in names:
        raise LifecycleError('project plugin discovery must be unset for profile cutover')
    raw = _read(root.fd, 'config.yaml')
    payloads = {}
    marker = {'schema_version': 1, 'owner': 'nunchi-hermes-lifecycle',
              'home': str(root.path), 'profile': profile}
    marker_path = '.nunchi-lifecycle-active.json'
    if _snapshot(root.fd, marker_path) is not None:
        if json.loads(_read(root.fd, marker_path)) != marker:
            raise LifecycleError('unattributed lifecycle scope marker')
        payloads[marker_path] = None
    if mode == 'activate':
        payloads[marker_path] = (json.dumps(marker, sort_keys=True) + '\n').encode()
    paths = default_config_paths(profile, hermes_home=root.path)
    data_path = str(paths.config.parent.relative_to(root.path))
    data_before = _snapshot(root.fd, data_path)
    if data_before is not None:
        allowed = {'config.json', 'config.json.sha256', 'state', '.lifecycle-owned.json',
                   '.nunchi-dashboard-config.lock', 'nunchi-dashboard-audit.jsonl'}
        extra = set(data_before['entries']) - allowed
        if any(not re.fullmatch(r'\.config\.json\.[0-9a-f]{64}\.nunchi-backup', name) for name in extra):
            raise LifecycleError('unmanaged Nunchi data entries')
        pin = _read(root.fd, str(paths.digest.relative_to(root.path))).decode().strip()
        existing = load_pinned_config(paths.config, expected_sha256=pin, hermes_profile=profile)
        if existing.state_directory != paths.state_directory:
            raise LifecycleError('existing state is outside the managed profile directory')
        payloads[data_path] = None
    if mode == 'activate':
        if not config or not config_sha256:
            raise LifecycleError('explicit V2 config and digest required')
        supplied = _external(config)
        loaded = load_pinned_config(config, expected_sha256=config_sha256, hermes_profile=profile)
        if _hash(supplied) != config_sha256 or _external(config) != supplied:
            raise LifecycleError('supplied config changed')
        if loaded.state_directory != paths.state_directory:
            raise LifecycleError('V2 state_directory must be the displayed profile-local default')
        if data_before is not None:
            raise LifecycleError('activation requires absent V2 data; retire first to preserve previous state')
        payloads[data_path] = {'config.json': supplied, 'config.json.sha256': (config_sha256 + '\n').encode()}
    # Do not silently leave predecessor copies discoverable. Full attribution is
    # checked below before any directory is retired.
    plugin_tree = _snapshot(root.fd, 'plugins')
    if plugin_tree:
        predecessors = list(_predecessors(root.fd, plugin_tree))
        for path in predecessors:
            payloads[path] = None
        if predecessors:
            import yaml
            host = yaml.safe_load(raw)
            legacy = host.get('nunchi', host.get('turnaware', {}))
            if not isinstance(legacy, dict):
                legacy = {}  # historical _nunchi_config: present invalid nunchi wins
            # Exact V1 bypassed HERMES_HOME. State false/null/empty values fall
            # back to ~/.hermes; only the log has disabled-value semantics.
            state_path = str(legacy.get('state_path') or '~/.hermes/nunchi-gate.state.json')
            log_value = legacy.get('log_path', '~/.hermes/logs/nunchi-gate.jsonl')
            log_path = '' if log_value is None else str(log_value).strip()
            selected_paths = [state_path]
            if log_path.lower() not in ('', '0', 'false', 'no', 'off', 'none'):
                selected_paths.append(log_path)
            for selected in selected_paths:
                path = Path(selected).expanduser()
                if not path.is_absolute() or '..' in path.parts:
                    raise LifecycleError('predecessor state/log outside selected home; retain and isolate it before cutover')
                # Only the already-validated home alias may be followed. Do
                # not resolve arbitrary external state or descendant symlinks.
                if path.is_relative_to(root.selected):
                    path = root.path / path.relative_to(root.selected)
                if not path.is_relative_to(root.path):
                    raise LifecycleError('predecessor state/log outside selected home; retain and isolate it before cutover')
                relative = str(path.relative_to(root.path))
                if relative not in ('nunchi-gate.state.json', 'logs/nunchi-gate.jsonl'):
                    raise LifecycleError('custom predecessor state path needs explicit ownership repair')
                if _snapshot(root.fd, relative) is not None:
                    payloads[relative] = None
        for name, entry in plugin_tree['entries'].items():
            if name in ('nunchi-dashboard', 'nunchi-v2-dashboard'):
                marker = '.nunchi-dashboard.json' if name == 'nunchi-dashboard' else '.nunchi-v2-dashboard.json'
                if not _bridge_is_owned(root.path / 'plugins' / name, marker):
                    raise LifecycleError('unattributed dashboard bridge')
                stamped = json.loads(_read(root.fd, 'plugins/' + name + '/' + marker))['assets']
                if set(stamped) != set(_assets()) or any(
                    _hash(_read(root.fd, 'plugins/' + name + '/dashboard/' + asset)) != expected
                    for asset, expected in stamped.items()
                ):
                    raise LifecycleError('dashboard asset differs from ownership stamp')
                payloads['plugins/' + name] = None

    if mode == 'activate':
        assets = _assets()
        marker = {'format': 1, 'assets': {n: _hash(b) for n, b in assets.items()}}
        payloads['plugins/nunchi-dashboard'] = {
            **{'dashboard/' + n: b for n, b in assets.items()},
            '.nunchi-dashboard.json': json.dumps(marker, sort_keys=True).encode(),
        }
    payloads['config.yaml'] = _config(raw, mode)
    operations = [{'path': path, 'before': _snapshot(root.fd, path),
                   'after_sha256': _payload_hash(payload)} for path, payload in payloads.items()]
    parents = set()
    identities = {}
    for op in operations:
        path = Path(op['path']).parent
        while str(path) != '.':
            if _snapshot(root.fd, str(path)) is None:
                parents.add(str(path))
            else:
                with _parent(root.fd, str(path)) as (parent, name):
                    identities[str(path)] = _identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
            path = path.parent
    return ({'schema_version': 1, 'mode': mode, 'profile': profile,
             'home': str(root.path), 'home_identity': root.identity,
             'v1_fallback': False, 'package_mutation': False,
             'predecessor_wheel': str(Path(predecessor_wheel).absolute()) if predecessor_wheel else None,
             'predecessor_package': _wheel_identity(predecessor_wheel) if predecessor_wheel else None,
             'parent_identities': identities,
             'package': _package(),
             'package_scope': 'shared interpreter; other profile consumers cannot be exhaustively inferred',
             'package_removal': 'separate operator action only after every consumer is stopped and retired',
             'discovery_before': plugin_tree,
             'config_source': str(Path(config).absolute()) if config else None,
             'config_sha256': config_sha256,
             'created_parents': sorted(parents, key=lambda p: (p.count('/'), p)),
             'operations': operations}, payloads)


def plan(*, home, mode, profile, config=None, config_sha256=None, predecessor_wheel=None):
    with _home(home) as root:
        return _build(root, mode, profile, config, config_sha256, predecessor_wheel)[0]


def _materialize(fd, name, payload):
    if isinstance(payload, bytes):
        _write(fd, name, payload)
    elif payload is not None:
        os.mkdir(name, 0o700, dir_fd=fd)
        child = os.open(name, _DIR, dir_fd=fd)
        try:
            for path, data in payload.items():
                parts = _parts(path)
                parent = os.dup(child)
                try:
                    for part in parts[:-1]:
                        try:
                            os.mkdir(part, 0o700, dir_fd=parent)
                        except FileExistsError:
                            pass
                        nxt = os.open(part, _DIR, dir_fd=parent)
                        os.close(parent)
                        parent = nxt
                    _write(parent, parts[-1], data)
                finally:
                    os.close(parent)
            os.fsync(child)
        finally:
            os.close(child)


def _checkpoint(stage):
    """No-op seam for deterministic failure and hard-exit tests."""


def _rename_noreplace(sp, sn, dp, dn):
    """Atomic no-replace rename, including directories; never emulate with stat.

    The lifecycle lock only coordinates lifecycle clients, not editors. Both
    supported POSIX kernels provide a directory-relative exclusive rename.
    Unsupported kernels/filesystems fail closed, retaining the journal.
    """
    import ctypes
    import errno
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = getattr(libc, 'renameatx_np', None)
        flag = 0x00000004  # RENAME_EXCL
    elif sys.platform == 'linux':
        rename = getattr(libc, 'renameat2', None)
        flag = 1  # RENAME_NOREPLACE
    else:
        rename = None
    if rename is None:
        raise LifecycleError('atomic no-replace rename unavailable')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(sp, os.fsencode(sn), dp, os.fsencode(dn), flag):
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise LifecycleError('destination appeared; conflict preserved')
        raise LifecycleError('atomic no-replace rename failed; journal retained')


def _move(root, src_fd, src, dst_fd, dst, expected):
    root.check()
    with _parent(src_fd, src) as (sp, sn), _parent(dst_fd, dst) as (dp, dn):
        if expected is None or _snapshot(sp, sn) != expected:
            raise LifecycleError('source drift at move; evidence preserved')
        root.check()
        _rename_noreplace(sp, sn, dp, dn)
        os.fsync(sp)
        os.fsync(dp)
        # An external writer may race the source check. Capture, do not destroy
        # it, and refuse to publish/restore anything over that conflict.
        if _snapshot(dp, dn) != expected:
            raise LifecycleError('source changed during move; captured conflict preserved')


def _transaction(store, transaction):
    if not re.fullmatch(r'[0-9a-f]{32}', transaction):
        raise LifecycleError('invalid transaction ID')
    return os.open(transaction, _DIR, dir_fd=store)


def _load(tx, root, *, bind=True):
    receipt = json.loads(_read(tx, 'receipt.json'))
    if (receipt['plan']['home_identity'] != root.identity or
            receipt['plan']['home'] != str(root.path) or
            digest(receipt['plan']) != receipt['plan_digest']):
        raise LifecycleError('receipt binding mismatch')
    if bind:
        root.bindings.update(receipt['plan']['parent_identities'])
        for path, identity in receipt.get('created_parent_identities', {}).items():
            if _snapshot(root.fd, path) is not None:
                root.bindings[path] = identity
        root.check()
    return receipt


def apply(*, home, plan, digest, stopped=False):
    if not stopped or globals()['digest'](plan) != digest:
        raise LifecycleError('stopped-process assertion and exact plan digest required')
    with _home(home) as root, _locked(root) as store:
        for name in os.listdir(store):
            if re.fullmatch(r'[0-9a-f]{32}', name):
                previous = _transaction(store, name)
                try:
                    if _load(previous, root, bind=False)['status'] not in ('applied', 'rolled_back'):
                        raise LifecycleError('pending transaction requires stopped rollback')
                finally:
                    os.close(previous)
        current, payloads = _build(root, plan['mode'], plan['profile'], plan['config_source'], plan['config_sha256'], plan['predecessor_wheel'])
        if current != plan:
            raise LifecycleError('plan drift; make a new plan')
        root.bindings.update(plan['parent_identities'])
        transaction = uuid.uuid4().hex
        os.mkdir(transaction, 0o700, dir_fd=store)
        tx = _transaction(store, transaction)
        root.bindings[STORE + '/' + transaction] = _identity(os.fstat(tx))
        try:
            receipt = {'schema_version': 1, 'transaction': transaction, 'plan': plan,
                       'plan_digest': digest, 'status': 'prepared', 'post': {},
                       'created_parent_identities': {}}
            root.check()
            _json_write(tx, 'receipt.json', receipt)
            os.fsync(store)
            try:
                if plan['predecessor_wheel']:
                    wheel = _external(plan['predecessor_wheel'])
                    if _hash(wheel) != plan['predecessor_package']['sha256']:
                        raise LifecycleError('predecessor wheel drift')
                    root.check()
                    _materialize(tx, 'predecessor-package', {Path(plan['predecessor_wheel']).name: wheel})
                for i, op in enumerate(plan['operations']):
                    root.check()
                    _materialize(tx, f'new-{i}', payloads[op['path']])
                    receipt['post'][op['path']] = _snapshot(tx, f'new-{i}')
                _json_write(tx, 'receipt.json', receipt)
                for path in plan['created_parents']:
                    root.check()
                    with _parent(root.fd, path) as (parent, name):
                        os.mkdir(name, 0o700, dir_fd=parent)
                        identity = _identity(os.stat(name, dir_fd=parent, follow_symlinks=False))
                        root.bindings[path] = identity
                        receipt['created_parent_identities'][path] = identity
                        os.fsync(parent)
                    _json_write(tx, 'receipt.json', receipt)
                for i, op in enumerate(plan['operations']):
                    if _snapshot(root.fd, op['path']) != op['before']:
                        raise LifecycleError('target drift before commit')
                    if op['before'] is not None:
                        _move(root, root.fd, op['path'], tx, f'before-{i}', op['before'])
                    _checkpoint('backed-up')
                    if receipt['post'][op['path']] is not None:
                        _move(root, tx, f'new-{i}', root.fd, op['path'], receipt['post'][op['path']])
                    _checkpoint('installed')
                root.check()
                for op in plan['operations']:
                    if _snapshot(root.fd, op['path']) != receipt['post'][op['path']]:
                        raise LifecycleError('target drift after commit')
                receipt['status'] = 'applied'
                _json_write(tx, 'receipt.json', receipt)
            except BaseException:
                _restore(root, tx, receipt)
                raise
            return receipt
        finally:
            os.close(tx)


def _restore(root, tx, receipt):
    root.check()
    # Preflight every target before restoring any: no partial clobber on drift.
    targets = {}
    for i, op in enumerate(receipt['plan']['operations']):
        target = _snapshot(root.fd, op['path'])
        targets[op['path']] = target
        backup = _snapshot(tx, f'before-{i}')
        if backup is not None and backup != op['before']:
            raise LifecycleError('backup drift')
        allowed = [op['before']]
        if op['path'] in receipt['post']:
            allowed.append(receipt['post'][op['path']])
        if backup is not None and receipt['status'] in ('prepared', 'rolling_back'):
            allowed.append(None)  # interrupted after backup, before install
        if target not in allowed:
            raise LifecycleError('later edits prevent rollback')
        if target != op['before'] and backup != op['before']:
            raise LifecycleError('before-image unavailable')
    # A parent created by us may only be removed under its recorded inode.
    for path in receipt['plan']['created_parents']:
        if _snapshot(root.fd, path) is not None and path not in receipt.get('created_parent_identities', {}):
            raise LifecycleError('unrecorded parent after interrupted preparation; preserve it for operator recovery')
    receipt['status'] = 'rolling_back'
    _json_write(tx, 'receipt.json', receipt)
    for i, op in reversed(list(enumerate(receipt['plan']['operations']))):
        target = targets[op['path']]
        if _snapshot(root.fd, op['path']) != target:
            raise LifecycleError('later edits prevent rollback')
        if target == op['before']:
            continue
        if target is not None:
            _move(root, root.fd, op['path'], tx, f'retired-{i}', target)
        if op['before'] is not None:
            _move(root, tx, f'before-{i}', root.fd, op['path'], op['before'])
    for path in reversed(receipt['plan']['created_parents']):
        root.check()
        try:
            with _parent(root.fd, path) as (parent, name):
                os.rmdir(name, dir_fd=parent)
                os.fsync(parent)
        except FileNotFoundError:
            pass
        root.bindings.pop(path, None)
    root.check()
    receipt['status'] = 'rolled_back'
    _json_write(tx, 'receipt.json', receipt)
    return receipt


def rollback(*, home, transaction, digest, stopped=False):
    if not stopped:
        raise LifecycleError('stopped-process assertion required')
    with _home(home) as root, _locked(root) as store:
        tx = _transaction(store, transaction)
        root.bindings[STORE + '/' + transaction] = _identity(os.fstat(tx))
        try:
            receipt = _load(tx, root)
            if receipt['plan_digest'] != digest or receipt['plan']['home_identity'] != root.identity:
                raise LifecycleError('receipt binding mismatch')
            return _restore(root, tx, receipt)
        finally:
            os.close(tx)


def verify(*, home, transaction):
    with _home(home) as root, _locked(root) as store:
        tx = _transaction(store, transaction)
        root.bindings[STORE + '/' + transaction] = _identity(os.fstat(tx))
        try:
            receipt = _load(tx, root)
            if receipt['status'] not in ('applied', 'rolled_back'):
                raise LifecycleError('interrupted transaction; stopped rollback required')
            for op in receipt['plan']['operations']:
                expected = op['before'] if receipt['status'] == 'rolled_back' else receipt['post'][op['path']]
                if _snapshot(root.fd, op['path']) != expected:
                    raise LifecycleError('transaction post-state drift')
            return {'schema_version': 1, 'ok': True, 'status': receipt['status'],
                    'transaction': transaction, 'running_process_adoption': False}
        finally:
            os.close(tx)


def lifecycle_dashboard_scope(home: Path, profile: str) -> bool:
    """Read the opt-in scope marker without following links or mutating config."""
    with _home(home) as root:
        name = '.nunchi-lifecycle-active.json'
        if _snapshot(root.fd, name) is None:
            return False
        expected = {'schema_version': 1, 'owner': 'nunchi-hermes-lifecycle',
                    'home': str(root.path), 'profile': profile}
        if json.loads(_read(root.fd, name)) != expected:
            raise LifecycleError('invalid lifecycle scope marker')
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(prog='nunchi-hermes-lifecycle',
                                     description='Plan a stopped, reversible profile cutover; never install packages or restart Hermes.')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('plan', 'apply', 'verify', 'rollback'):
        sub = commands.add_parser(command)
        sub.add_argument('--hermes-home', type=Path, required=True)
        sub.add_argument('--hermes-python', type=Path, required=True)
        if command == 'plan':
            sub.add_argument('--mode', choices=('activate', 'retire'), required=True)
            sub.add_argument('--profile', required=True)
            sub.add_argument('--config', type=Path)
            sub.add_argument('--config-sha256')
            sub.add_argument('--wheel-sha256', required=True)
            sub.add_argument('--predecessor-wheel', type=Path)
        if command == 'apply':
            sub.add_argument('--plan', type=Path, required=True)
        if command in ('apply', 'rollback'):
            sub.add_argument('--plan-sha256', required=True)
            sub.add_argument('--processes-stopped', action='store_true', required=True)
        if command in ('verify', 'rollback'):
            sub.add_argument('--transaction', required=True)
        if command == 'rollback':
            sub.add_argument('--mode', choices=('restore',), required=True)
    args = parser.parse_args(argv)
    try:
        if args.hermes_python.absolute() != Path(sys.executable).absolute():
            raise LifecycleError('run with the explicitly selected Hermes interpreter')
        if args.command == 'plan':
            candidate = _package()
            if not candidate['installed_wheel'] or candidate['wheel_sha256'] != args.wheel_sha256:
                raise LifecycleError('install the exact selected wheel in the Hermes interpreter first')
            result = plan(home=args.hermes_home, mode=args.mode, profile=args.profile,
                          config=args.config, config_sha256=args.config_sha256,
                          predecessor_wheel=args.predecessor_wheel)
            if any(op['path'].startswith('plugins/') and op['before'] and
                   'plugin.yaml' in op['before'].get('entries', {}) for op in result['operations']):
                if not args.predecessor_wheel:
                    raise LifecycleError('retain and supply the exact predecessor wheel before cutover')
            result = {'schema_version': 1, 'plan': result, 'plan_sha256': digest(result)}
        elif args.command == 'apply':
            document = json.loads(_external(args.plan))
            result = apply(home=args.hermes_home, plan=document['plan'],
                           digest=args.plan_sha256, stopped=args.processes_stopped)
        elif args.command == 'rollback':
            result = rollback(home=args.hermes_home, transaction=args.transaction,
                              digest=args.plan_sha256, stopped=args.processes_stopped)
        else:
            result = verify(home=args.hermes_home, transaction=args.transaction)
    except LifecycleError as exc:
        print(json.dumps({'schema_version': 1, 'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1
    except Exception:
        # YAML/JSON/OS errors may embed private values or filenames. Do not echo.
        print(json.dumps({'schema_version': 1, 'ok': False,
                          'error': 'lifecycle refused unsafe, unavailable or malformed input; no values logged'}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
