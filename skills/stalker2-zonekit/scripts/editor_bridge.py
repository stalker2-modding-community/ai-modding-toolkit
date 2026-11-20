"""Opt-in localhost HTTP listener for the open STALKER 2 Zone Kit editor (127.0.0.1 only).

Starts only when manually launched by the user inside an active Stalker2ModEditor Output Log
session and should be stopped with stop_bridge() when finished. Auto-skips inside
commandlet/unattended runs (-run=Cook, -run=pythonscript, -unattended, -nullrhi). Disabled
when the editor is closed.

Security controls & limits:
  - Binds loopback 127.0.0.1:18777 only (overridable with S2_BRIDGE_PORT).
  - Fail-closed per-boot random bearer token (header X-S2-Bridge-Token), locked on Windows
    via icacls to the current user account; HTTP POST rejects with 403 if the token is empty
    or stale (e.g. after a module reload).
  - Single-mod write lock: set_mi_params refuses all writes unless start_bridge(mod="<Mod>")
    or S2_BRIDGE_MOD names the allowed mod root (other mods and /Game/ are refused).
  - Pre-queue payload & finite-timeout validation (HTTP 400 before queueing) and non-queueing
    single-slot Slate dispatch (HTTP 429 when busy, HTTP 504 on timeout; already-started tasks
    keep running on the main thread until finished).
  - Best-effort per-task load/save speed bump (_BudgetGuard on EditorAssetLibrary/Utils,
    max_loads <= 50, max_saves <= 10); bypassable by C++/load_object, NOT a security sandbox.
  - Arbitrary script execution (run_script) stays disabled unless started explicitly with both
    allow_run_script=True and script_root="<local dir>" (no env-var toggle; UNC/network paths
    and scripts outside script_root are refused). Script dir is prepended to sys.path.

Example inside the Zone Kit Output Log (Python):
    import sys; sys.path.append(r"<skill scripts folder>")
    import editor_bridge
    editor_bridge.start_bridge()                  # read-only + scan_mod
    editor_bridge.start_bridge(mod="MyMod")       # allow set_mi_params under /MyMod/
"""
import contextlib
import ctypes
import io
import json
import math
import os
import queue
import re
import runpy
import secrets
import subprocess
import sys
import threading
import traceback

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import unreal
except ImportError:
    unreal = None

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 18777
MAX_LOAD_CAP = 50
MAX_SAVE_CAP = 10
MOD_NAME_RX = re.compile(r'^[A-Za-z0-9_]+$')
BUILTIN_ROOTS = {'Game', 'Engine', 'Script', 'Temp', 'Memory', 'Transient', 'Niagara', 'ControlRig', 'RigVM'}

_task_queue = queue.Queue(maxsize=1)
_state_lock = threading.Lock()
_task_in_flight = False
_bridge_token = ''
_token_file_in_use = ''
_httpd = None
_server_thread = None
_slate_handle = None
_allow_run_script = False
_allowed_mod = ''
_allowed_script_root = ''


def _is_network_path(path):
    raw = str(path or '').strip()
    if not raw:
        return False
    if raw.startswith('\\\\') or raw.startswith('//'):
        return True
    resolved = os.path.realpath(raw)
    if resolved.startswith('\\\\') or resolved.startswith('//'):
        return True
    if os.name == 'nt':
        cleaned = resolved[4:] if resolved.startswith('\\\\?\\') else resolved
        drive, _ = os.path.splitdrive(cleaned)
        if drive:
            try:
                if ctypes.windll.kernel32.GetDriveTypeW(drive + '\\') == 4:  # DRIVE_REMOTE
                    return True
            except Exception:
                pass
    return False


def _ue():
    ue = unreal if unreal is not None else sys.modules.get('unreal')
    if ue is None:
        raise RuntimeError('editor_bridge requires the Zone Kit Unreal Editor Python runtime')
    return ue


def default_token_file():
    override = os.environ.get('S2_BRIDGE_TOKEN_FILE', '').strip()
    if override:
        return os.path.abspath(override)
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'Stalker2', 'Saved', 's2_editor_bridge.token')


def _log(msg, level='info'):
    ue = unreal if unreal is not None else sys.modules.get('unreal')
    if ue is not None:
        fn = getattr(ue, 'log_warning' if level == 'warn' else 'log', None)
        if callable(fn):
            fn(msg)
            return
    print(msg)


def is_commandlet_or_unattended():
    """Return True inside cook/commandlet/unattended runs so startup skips automatic binding."""
    ue = unreal if unreal is not None else sys.modules.get('unreal')
    args_low = ' '.join(sys.argv).lower()
    cmd_low = ''
    if ue is not None:
        sys_lib = getattr(ue, 'SystemLibrary', None)
        if sys_lib is not None:
            try:
                cmd_low = str(sys_lib.get_command_line()).lower()
            except Exception:
                cmd_low = ''
            try:
                if sys_lib.is_unattended():
                    return True
            except Exception:
                pass
    combined = '%s %s' % (args_low, cmd_low)
    return any(flag in combined for flag in ('-run=', '-unattended', '-nullrhi'))


class _BudgetGuard:
    """Best-effort speed bump wrapping Python load/save helpers for one main-thread task.

    Not a hard safety limit: direct C++ APIs, unreal.load_object, or unwrapped subsystems
    bypass this counter.
    """

    def __init__(self, max_loads=25, max_saves=5):
        self.max_loads = min(max(0, int(max_loads)), MAX_LOAD_CAP)
        self.max_saves = min(max(0, int(max_saves)), MAX_SAVE_CAP)
        self.loads = 0
        self.saves = 0
        self._originals = []

    def _record(self, kind, count):
        if kind == 'load':
            self.loads += count
            if self.loads > self.max_loads:
                raise RuntimeError('Asset load budget exceeded (%d/%d)' % (self.loads, self.max_loads))
        else:
            self.saves += count
            if self.saves > self.max_saves:
                raise RuntimeError('Asset save budget exceeded (%d/%d)' % (self.saves, self.max_saves))

    def _wrap(self, obj, attr, kind, batch_arg=None):
        if obj is None or not hasattr(obj, attr):
            return
        orig = getattr(obj, attr)
        self._originals.append((obj, attr, orig))

        def wrapped(*args, **kwargs):
            cnt = 1
            if batch_arg is not None and len(args) > batch_arg and isinstance(args[batch_arg], (list, tuple, set)):
                cnt = max(1, len(args[batch_arg]))
            self._record(kind, cnt)
            return orig(*args, **kwargs)

        try:
            is_static = isinstance(getattr(obj, '__dict__', {}).get(attr), staticmethod)
            setattr(obj, attr, staticmethod(wrapped) if is_static else wrapped)
        except TypeError:
            self._originals.pop()

    def __enter__(self):
        ue = _ue()
        eal = getattr(ue, 'EditorAssetLibrary', None)
        elsu = getattr(ue, 'EditorLoadingAndSavingUtils', None)
        self._wrap(ue, 'load_asset', 'load')
        self._wrap(eal, 'load_asset', 'load')
        self._wrap(eal, 'save_loaded_asset', 'save')
        self._wrap(eal, 'save_loaded_assets', 'save', batch_arg=0)
        self._wrap(eal, 'save_asset', 'save')
        self._wrap(eal, 'save_directory', 'save')
        self._wrap(elsu, 'save_packages', 'save', batch_arg=0)
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        for obj, attr, orig in reversed(self._originals):
            try:
                setattr(obj, attr, orig)
            except Exception:
                pass
        self._originals.clear()


def _lock_token_acl(path):
    """Restrict token file NTFS ACLs on Windows to the active user account."""
    if os.name != 'nt':
        return
    user = os.environ.get('USERNAME', '')
    dom = os.environ.get('USERDOMAIN', '')
    principal = ('%s\\%s' % (dom, user)) if (dom and user) else user
    if not principal:
        return
    try:
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        subprocess.run(
            ['icacls', path, '/inheritance:r', '/grant:r', '%s:F' % principal],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            check=False,
        )
    except Exception as e:
        _log('[s2_bridge] failed to restrict ACL on %s: %s' % (path, e), level='warn')


def _is_allowed_mod_package(pkg, allowed_mod):
    if not allowed_mod:
        return False
    parts = [p for p in str(pkg or '').split('/') if p]
    if len(parts) < 2 or '..' in parts:
        return False
    return parts[0].lower() == allowed_mod.lower()


def _action_get_selected(_payload):
    ue = _ue()
    selected = ue.EditorUtilityLibrary.get_selected_assets() or []
    items = []
    for asset in selected:
        outer = asset.get_outer()
        pkg = outer.get_name() if outer else ''
        items.append({
            'package': pkg,
            'name': asset.get_name() if hasattr(asset, 'get_name') else str(asset),
            'class': asset.get_class().get_name() if hasattr(asset, 'get_class') else '',
        })
    return {'status': 'ok', 'selected': items}


def _action_scan_mod(payload):
    ue = _ue()
    mod = str(payload.get('mod') or '').strip()
    if not MOD_NAME_RX.match(mod):
        return {'status': 'error', 'error': 'mod must match ^[A-Za-z0-9_]+$'}
    reg = ue.AssetRegistryHelpers.get_asset_registry()
    reg.scan_paths_synchronous(['/%s/' % mod], True)
    return {'status': 'ok', 'scanned': '/%s/' % mod}


def _action_list_assets(payload):
    ue = _ue()
    pkg_path = str(payload.get('path') or '/Game/').strip()
    if not pkg_path.startswith('/'):
        return {'status': 'error', 'error': 'path must start with /'}
    recursive = bool(payload.get('recursive', True))
    limit = min(max(1, int(payload.get('limit', 100))), 500)
    eal = ue.EditorAssetLibrary
    assets = eal.list_assets(pkg_path, recursive=recursive, include_folder=False) or []
    truncated = len(assets) > limit
    return {'status': 'ok', 'path': pkg_path, 'total': len(assets), 'truncated': truncated, 'assets': list(assets[:limit])}


def _action_audit_cross_mod(payload):
    ue = _ue()
    reg = ue.AssetRegistryHelpers.get_asset_registry()
    pkgs = payload.get('assets')
    if not pkgs:
        pkgs = [
            a.get_outer().get_name()
            for a in (ue.EditorUtilityLibrary.get_selected_assets() or [])
            if a.get_outer()
        ]
    opts = ue.AssetRegistryDependencyOptions(
        include_soft_package_references=False,
        include_hard_package_references=True,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False,
    )
    findings = []
    for pkg in pkgs:
        parts = str(pkg).strip('/').split('/')
        src_mod = parts[0] if parts else ''
        deps = [str(d) for d in (reg.get_dependencies(pkg, opts) or [])]
        foreign = []
        for dep in deps:
            root = dep.strip('/').split('/')[0] if dep.strip('/') else ''
            if root and root != src_mod and root not in BUILTIN_ROOTS:
                foreign.append(dep)
        findings.append({'package': pkg, 'foreign_deps': foreign})
    return {'status': 'ok', 'findings': findings}


def _action_inspect_mi(payload):
    ue = _ue()
    asset_path = str(payload.get('asset') or '').strip()
    if not asset_path.startswith('/'):
        return {'status': 'error', 'error': 'asset package path must start with /'}
    mi = ue.EditorAssetLibrary.load_asset(asset_path)
    if mi is None:
        return {'status': 'error', 'error': 'asset not found: %s' % asset_path}
    parent = mi.get_editor_property('parent') if hasattr(mi, 'get_editor_property') else None
    scalars = []
    for p in mi.get_editor_property('scalar_parameter_values') or []:
        info = p.get_editor_property('parameter_info')
        scalars.append({'name': str(info.get_editor_property('name')), 'value': float(p.get_editor_property('parameter_value'))})
    vectors = []
    for p in mi.get_editor_property('vector_parameter_values') or []:
        info = p.get_editor_property('parameter_info')
        c = p.get_editor_property('parameter_value')
        vectors.append({'name': str(info.get_editor_property('name')), 'value': [float(c.r), float(c.g), float(c.b), float(c.a)]})
    textures = []
    for p in mi.get_editor_property('texture_parameter_values') or []:
        info = p.get_editor_property('parameter_info')
        tv = p.get_editor_property('parameter_value')
        textures.append({'name': str(info.get_editor_property('name')), 'value': tv.get_path_name() if tv else 'None'})
    return {
        'status': 'ok',
        'asset': asset_path,
        'parent': parent.get_path_name() if parent else 'None',
        'scalars': scalars,
        'vectors': vectors,
        'textures': textures,
    }


def _action_set_mi_params(payload):
    ue = _ue()
    if not _allowed_mod:
        return {
            'status': 'error',
            'error': 'writes are disabled; restart bridge with start_bridge(mod="<ModName>") or set S2_BRIDGE_MOD',
        }
    asset_path = str(payload.get('asset') or '').strip()
    if not _is_allowed_mod_package(asset_path, _allowed_mod):
        return {'status': 'error', 'error': 'refusing write outside allowed mod /%s/: %s' % (_allowed_mod, asset_path)}
    mi = ue.EditorAssetLibrary.load_asset(asset_path)
    if mi is None:
        return {'status': 'error', 'error': 'asset not found: %s' % asset_path}
    mel = ue.MaterialEditingLibrary
    updated_scalars = {}
    for k, v in (payload.get('scalars') or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, str(k), float(v))
        updated_scalars[str(k)] = float(mel.get_material_instance_scalar_parameter_value(mi, str(k)))
    updated_vectors = {}
    for k, rgba in (payload.get('vectors') or {}).items():
        r, g, b, a = [float(x) for x in rgba]
        mel.set_material_instance_vector_parameter_value(mi, str(k), ue.LinearColor(r, g, b, a))
        out_c = mel.get_material_instance_vector_parameter_value(mi, str(k))
        updated_vectors[str(k)] = [float(out_c.r), float(out_c.g), float(out_c.b), float(out_c.a)]
    mel.update_material_instance(mi)
    saved = False
    if payload.get('save'):
        saved = bool(ue.EditorAssetLibrary.save_loaded_asset(mi))
    return {'status': 'ok', 'asset': asset_path, 'scalars': updated_scalars, 'vectors': updated_vectors, 'saved': saved}


def _action_run_script(payload):
    """Execute a local .py file inside script_root within the live editor (bearer token holders only).

    Prepends the script directory to sys.path while running so local helper imports resolve first.
    """
    if not (_allow_run_script and _allowed_script_root):
        return {
            'status': 'error',
            'error': 'run_script is disabled; start bridge with allow_run_script=True and script_root="<local dir>".',
        }
    raw_script = str(payload.get('script') or '').strip()
    if not raw_script:
        return {'status': 'error', 'error': 'script path is required'}
    if _is_network_path(raw_script):
        return {'status': 'error', 'error': 'refusing network/UNC script path: %s' % raw_script}
    script = os.path.realpath(raw_script)
    try:
        in_root = os.path.commonpath([os.path.normcase(_allowed_script_root), os.path.normcase(script)]) == os.path.normcase(_allowed_script_root)
    except ValueError:
        in_root = False
    if not in_root:
        return {'status': 'error', 'error': 'script %s is outside allowed script_root %s' % (script, _allowed_script_root)}
    if not os.path.isfile(script) or not script.lower().endswith('.py'):
        return {'status': 'error', 'error': 'script must be an existing .py file: %s' % script}
    script_args = [str(a) for a in (payload.get('args') or [])]
    s2_env = {str(k): str(v) for k, v in (payload.get('env') or {}).items() if str(k).startswith('S2_')}

    old_argv = list(sys.argv)
    old_path = list(sys.path)
    old_env = {k: os.environ.get(k) for k in s2_env}
    buf = io.StringIO()
    ue = _ue()
    try:
        for k, v in s2_env.items():
            os.environ[k] = v
        sys.argv = [script] + script_args
        sdir = os.path.dirname(script)
        if sdir not in sys.path:
            sys.path.insert(0, sdir)
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            runpy.run_path(script, init_globals={'unreal': ue}, run_name='__main__')
    except SystemExit as se:
        code = se.code if isinstance(se.code, int) else 1
        if code:
            return {'status': 'error', 'error': 'script exited %s' % code, 'output': buf.getvalue()}
    finally:
        sys.argv = old_argv
        sys.path[:] = old_path
        for k, prev in old_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev
    return {'status': 'ok', 'script': script, 'output': buf.getvalue()}


ACTIONS = {
    'get_selected': _action_get_selected,
    'scan_mod': _action_scan_mod,
    'list_assets': _action_list_assets,
    'audit_cross_mod_refs': _action_audit_cross_mod,
    'inspect_material_instance': _action_inspect_mi,
    'set_mi_params': _action_set_mi_params,
    'run_script': _action_run_script,
}


def _execute_on_main_thread(payload):
    action = str(payload.get('action') or '')
    fn = ACTIONS.get(action)
    if fn is None:
        return {'status': 'error', 'error': 'unknown action %r (valid: %s)' % (action, ', '.join(sorted(ACTIONS)))}
    max_loads = int(payload.get('max_loads', 25))
    max_saves = int(payload.get('max_saves', 5))
    try:
        with _BudgetGuard(max_loads=max_loads, max_saves=max_saves) as budget:
            out = fn(payload)
            if isinstance(out, dict):
                out['budget'] = {
                    'loads': budget.loads,
                    'max_loads': budget.max_loads,
                    'saves': budget.saves,
                    'max_saves': budget.max_saves,
                }
            return out
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'traceback': traceback.format_exc()}


def _make_handler(port_bound, expected_token):
    class BridgeHandler(BaseHTTPRequestHandler):
        def log_message(self, _fmt, *_args):
            pass

        def _send_json(self, code, obj):
            body = json.dumps(obj).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ('/ping', '/status'):
                with _state_lock:
                    busy = _task_in_flight
                self._send_json(200, {
                    'status': 'online',
                    'busy': busy,
                    'auth_required': True,
                    'token_active': bool(expected_token and _bridge_token),
                    'allowed_mod': _allowed_mod or None,
                    'run_script_enabled': bool(_allow_run_script and _allowed_script_root),
                    'script_root': _allowed_script_root or None,
                    'port': port_bound,
                })
            else:
                self._send_json(404, {'error': 'Not found'})

        def do_POST(self):
            global _task_in_flight
            req_token = self.headers.get('X-S2-Bridge-Token', '')
            if not expected_token or not _bridge_token or not secrets.compare_digest(req_token, expected_token):
                self._send_json(403, {'status': 'forbidden', 'error': 'Invalid, missing, or inactive X-S2-Bridge-Token'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length > 1_048_576:
                    self._send_json(413, {'error': 'Request body too large'})
                    return
                raw = self.rfile.read(length).decode('utf-8') if length > 0 else '{}'
                payload = json.loads(raw)
            except Exception as e:
                self._send_json(400, {'error': 'Invalid JSON: %s' % e})
                return
            if not isinstance(payload, dict):
                self._send_json(400, {'error': 'Request JSON must be an object'})
                return
            raw_timeout = payload.get('timeout', 30.0)
            if isinstance(raw_timeout, bool):
                self._send_json(400, {'error': 'Invalid timeout: boolean is not allowed'})
                return
            try:
                timeout_val = float(raw_timeout)
            except (TypeError, ValueError):
                self._send_json(400, {'error': 'Invalid timeout value: %r' % (raw_timeout,)})
                return
            if not math.isfinite(timeout_val):
                self._send_json(400, {'error': 'Invalid timeout value: must be finite'})
                return
            timeout_s = min(max(1.0, timeout_val), 120.0)

            with _state_lock:
                if _task_in_flight:
                    self._send_json(429, {'status': 'busy', 'error': 'Another task is executing on the editor main thread'})
                    return
                _task_in_flight = True

            res_q = queue.Queue(maxsize=1)
            cancel_ev = threading.Event()
            try:
                _task_queue.put_nowait((payload, res_q, cancel_ev))
            except queue.Full:
                with _state_lock:
                    _task_in_flight = False
                self._send_json(429, {'status': 'busy', 'error': 'Bridge task slot is full'})
                return

            try:
                res = res_q.get(timeout=timeout_s)
                self._send_json(200, res)
            except queue.Empty:
                cancel_ev.set()
                self._send_json(504, {
                    'status': 'timeout',
                    'error': 'Timed out waiting for Slate main-thread result; queued unstarted tasks are skipped, while an already-started task keeps running until finished',
                })

    return BridgeHandler


def _on_slate_tick(_delta_time):
    global _task_in_flight
    try:
        payload, res_q, cancel_ev = _task_queue.get_nowait()
    except queue.Empty:
        return
    try:
        if cancel_ev.is_set():
            with contextlib.suppress(queue.Full):
                res_q.put_nowait({'status': 'cancelled', 'error': 'Caller timed out before main-thread execution'})
            return
        res = _execute_on_main_thread(payload)
        with contextlib.suppress(queue.Full):
            res_q.put_nowait(res)
    finally:
        with _state_lock:
            _task_in_flight = False


def start_bridge(host=DEFAULT_HOST, port=None, force=False, allow_run_script=False, token_file=None, mod=None, script_root=None):
    """Start the opt-in localhost HTTP listener inside an active interactive Zone Kit editor session."""
    global _bridge_token, _token_file_in_use, _httpd, _server_thread, _slate_handle, _allow_run_script, _allowed_mod, _allowed_script_root
    ue = _ue()
    if not force and is_commandlet_or_unattended():
        _log('[s2_bridge] Skipping bridge startup in commandlet/unattended process.')
        return False
    if host not in ('127.0.0.1', 'localhost'):
        raise ValueError('Refusing non-loopback host %r (must be 127.0.0.1)' % host)
    resolved_mod = str(mod if mod is not None else os.environ.get('S2_BRIDGE_MOD', '')).strip()
    if resolved_mod and not MOD_NAME_RX.match(resolved_mod):
        raise ValueError('mod must match ^[A-Za-z0-9_]+$: %r' % resolved_mod)
    resolved_script_root = ''
    if allow_run_script:
        if not script_root or not str(script_root).strip():
            raise ValueError('allow_run_script=True requires script_root pointing to a local directory')
        raw_root = str(script_root).strip()
        if _is_network_path(raw_root):
            raise ValueError('Refusing network/UNC script_root: %r' % script_root)
        resolved_script_root = os.path.realpath(raw_root)
        if not os.path.isdir(resolved_script_root):
            raise ValueError('script_root does not exist or is not a directory: %r' % script_root)
    if _server_thread is not None and _server_thread.is_alive():
        _log('[s2_bridge] Already running on %s (use restart_bridge(...) to change options)' % _httpd.server_address[1])
        return True

    bind_port = int(port if port is not None else os.environ.get('S2_BRIDGE_PORT', DEFAULT_PORT))
    token = secrets.token_hex(24)
    try:
        _httpd = ThreadingHTTPServer((host, bind_port), _make_handler(bind_port, token))
    except OSError as e:
        _log('[s2_bridge] Could not bind %s:%d: %s' % (host, bind_port, e), level='warn')
        return False

    _allowed_mod = resolved_mod
    _allow_run_script = bool(allow_run_script)
    _allowed_script_root = resolved_script_root
    _bridge_token = token
    _token_file_in_use = os.path.abspath(token_file) if token_file else default_token_file()
    try:
        os.makedirs(os.path.dirname(_token_file_in_use), exist_ok=True)
        with open(_token_file_in_use, 'w', encoding='utf-8') as tf:
            tf.write(_bridge_token)
        _lock_token_acl(_token_file_in_use)
    except Exception as e:
        _log('[s2_bridge] Failed writing token file %s: %s' % (_token_file_in_use, e), level='warn')

    _server_thread = threading.Thread(target=_httpd.serve_forever, name='S2_Editor_Bridge', daemon=True)
    _server_thread.start()
    _slate_handle = ue.register_slate_post_tick_callback(_on_slate_tick)
    _log('[s2_bridge] Listening on http://%s:%d (token auth enabled, allowed_mod=%s, run_script=%s, script_root=%s)'
         % (host, bind_port, _allowed_mod or 'none', _allow_run_script, _allowed_script_root or 'none'))
    return True


def stop_bridge():
    """Stop the localhost HTTP listener, unregister Slate tick callback, and remove the token file."""
    global _httpd, _server_thread, _slate_handle, _bridge_token, _token_file_in_use, _allow_run_script, _allowed_mod, _allowed_script_root
    ue = unreal if unreal is not None else sys.modules.get('unreal')
    if _slate_handle is not None and ue is not None:
        try:
            ue.unregister_slate_post_tick_callback(_slate_handle)
        except Exception:
            pass
    _slate_handle = None
    if _httpd is not None:
        try:
            _httpd.shutdown()
            _httpd.server_close()
        except Exception:
            pass
        _httpd = None
    _server_thread = None
    _bridge_token = ''
    _allow_run_script = False
    _allowed_mod = ''
    _allowed_script_root = ''
    if _token_file_in_use and os.path.isfile(_token_file_in_use):
        try:
            os.remove(_token_file_in_use)
        except OSError:
            pass
    _token_file_in_use = ''
    _log('[s2_bridge] Stopped.')


def restart_bridge(**kwargs):
    stop_bridge()
    return start_bridge(**kwargs)


def main(argv):
    if '-h' in argv or '--help' in argv or not argv:
        print(__doc__)
        return 0
    print('Start editor_bridge.start_bridge() from inside the Zone Kit editor Python runtime.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
