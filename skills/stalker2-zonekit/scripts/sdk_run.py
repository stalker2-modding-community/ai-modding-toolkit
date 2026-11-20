r"""Run a Python script inside the STALKER 2 Zone Kit editor, headless.

The Zone Kit (UE 5.5.4) ships PythonScriptPlugin and EditorScriptingUtilities enabled, so the editor will execute a script
with no GUI. This script starts the real editor binary directly (the launcher stub Stalker2ModEditor.exe can be blocked by
Smart App Control):

    <kit>/Stalker2/Binaries/Win64/Stalker2ModEditor-Win64-Shipping-Cmd.exe <uproject> -run=pythonscript -script=<file>
        -unattended -nosplash -nopause

Startup costs about six minutes (the editor parses 151k gamedata cfg files every launch), so batch the work into one script.
Everything the script prints lands in the engine log as `LogPython: ...`. The log is
%LOCALAPPDATA%/Stalker2/Saved/Logs/Stalker2.log and the editor rotates the previous one to Stalker2-backup-*.log on start,
so the current log always belongs to the current run.

The editor is started DETACHED: a run outlives the shell that launched it, so a long run cannot be killed by session teardown.
Poll it from a later call instead of holding a process open.

    python sdk_run.py <script.py>            launch, then poll until that run ends
    python sdk_run.py --launch <script.py>   launch and return immediately
    python sdk_run.py --wait                 poll the run that is already going (any running kit editor)

Opt-in live bridge client (only when editor_bridge.start_bridge() was started inside an open kit session):
    python sdk_run.py --bridge-status [--port 18777]
    python sdk_run.py --bridge-action <action> [--payload <json|@file>] [--port 18777]
    python sdk_run.py --bridge <script.py> [args...] [--port 18777]

A headless run can read anything and can edit and save assets that are already in a mod folder (materials, material
instances, Blueprint class defaults). It cannot save a /Game asset (no mod is selected, so the checkout has nowhere to go),
add Blueprint graph nodes or edit Niagara: see the stalker2-zonekit skill. Close the kit editor first for headless runs or cooks.
Windows only (except --bridge* flags when pointing at an active loopback port). Needs the Zone Kit (see s2paths.py).
"""
import csv, json, os, subprocess, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2paths

EDITOR_CMD = 'Stalker2ModEditor-Win64-Shipping-Cmd.exe'
EDITORS = {'stalker2modeditor-win64-shipping.exe', EDITOR_CMD.lower()}      # the GUI editor and the command line one
DETACHED = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW


def log_path():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'Stalker2', 'Saved', 'Logs', 'Stalker2.log')


def editor_pids():
    """PIDs of running kit editors. CSV output keeps full image names (the table format cuts them to 25 characters)."""
    out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, errors='replace').stdout
    return [int(row[1]) for row in csv.reader(out.splitlines())
            if len(row) >= 2 and row[1].isdigit() and row[0].lower() in EDITORS]


def alive(proc=None):
    """proc given: is that started process still running; else: is any kit editor running."""
    if proc is not None:
        return proc.poll() is None
    return bool(editor_pids())


def launch(script):
    script = os.path.abspath(script)
    if not os.path.isfile(script):
        raise SystemExit('no such script: ' + script)
    kit = s2paths.kit_dir()
    exe = os.path.join(kit, 'Stalker2', 'Binaries', 'Win64', EDITOR_CMD)
    uproject = os.path.join(kit, 'Stalker2', 'Stalker2.uproject')
    if not os.path.isfile(exe):
        raise SystemExit('no editor binary at %s' % exe)
    running = editor_pids()
    if running:
        raise SystemExit('a kit editor is already running (pid %s); wait for it or close it' % ', '.join(map(str, running)))
    cmd = [exe, uproject, '-run=pythonscript', '-script=' + script,
           '-unattended', '-nosplash', '-nopause', '-stdout', '-NoLogTimes']
    p = subprocess.Popen(cmd, creationflags=DETACHED, close_fds=True, cwd=kit,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('launched %s detached (editor pid %d)' % (os.path.basename(script), p.pid))
    return p


def read_log():
    log = log_path()
    if not os.path.isfile(log):
        return []
    with open(log, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read().splitlines()


def report():
    lines = read_log()
    out = [l.split('LogPython: ', 1)[1] for l in lines if 'LogPython: ' in l and 'Warning:' not in l and 'Display:' not in l]
    err = [l for l in lines if ': Error: ' in l and 'DerivedDataCache' not in l and 'AssetReferenceRestrictions' not in l]
    print('\n'.join(out))
    if err:
        print('--- engine errors ---')
        print('\n'.join(err[-15:]))
    return out


def wait(proc=None, timeout=1800):
    """Poll until the run ends. proc: the process launch() started (exact); None: any kit editor, giving up after 90 s
    if none ever shows."""
    start = time.time()
    started = proc is not None
    while time.time() - start < timeout:
        if alive(proc):
            started = True
        elif started or time.time() - start > 90:
            break                      # the run ended (or never started)
        time.sleep(5)
    out = report()
    print('--- %.0f s, %d python lines, editor %s ---'
          % (time.time() - start, len(out), 'still running' if alive(proc) else 'exited'))
    return out


def _bridge_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _bridge_token():
    override = os.environ.get('S2_BRIDGE_TOKEN_FILE', '').strip()
    if override:
        tok_path = os.path.abspath(override)
    else:
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
        tok_path = os.path.join(base, 'Stalker2', 'Saved', 's2_editor_bridge.token')
    if os.path.isfile(tok_path):
        with open(tok_path, 'r', encoding='utf-8') as fh:
            return fh.read().strip()
    return ''


def _pop_port(args):
    port = int(os.environ.get('S2_BRIDGE_PORT', '18777'))
    out = []
    i = 0
    while i < len(args):
        if args[i] == '--port':
            if i + 1 >= len(args) or not args[i + 1].isdigit():
                raise SystemExit('--port needs an integer port number')
            port = int(args[i + 1])
            i += 2
            continue
        out.append(args[i])
        i += 1
    return port, out


def bridge_status(port=18777):
    url = 'http://127.0.0.1:%d/ping' % port
    try:
        with _bridge_opener().open(url, timeout=2.0) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='replace'))
        print(json.dumps(data, indent=2))
        return 0 if data.get('status') == 'online' else 1
    except (OSError, ValueError, urllib.error.URLError) as e:
        print('bridge offline on 127.0.0.1:%d (%s)' % (port, e), file=sys.stderr)
        return 1


def bridge_call(payload, port=18777, timeout=35.0):
    url = 'http://127.0.0.1:%d/' % port
    body = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    tok = _bridge_token()
    if tok:
        headers['X-S2-Bridge-Token'] = tok
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with _bridge_opener().open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')
        if e.code == 403:
            raise SystemExit('bridge auth failed (HTTP 403) - check s2_editor_bridge.token: %s' % detail)
        if e.code == 429:
            raise SystemExit('bridge busy (HTTP 429) - refused to queue behind another editor task: %s' % detail)
        if e.code == 504:
            raise SystemExit('bridge timeout (HTTP 504) waiting for Slate main-thread tick: %s' % detail)
        raise SystemExit('bridge HTTP %d: %s' % (e.code, detail))
    except (OSError, ValueError, urllib.error.URLError) as e:
        raise SystemExit('bridge request failed on 127.0.0.1:%d (%s): start editor_bridge.start_bridge() inside the editor first'
                         % (port, e))


def bridge_action(args, port):
    if not args:
        raise SystemExit('--bridge-action needs an action name')
    action = args[0]
    payload = {}
    i = 1
    while i < len(args):
        if args[i] == '--payload':
            if i + 1 >= len(args):
                raise SystemExit('--payload needs JSON or @file.json')
            raw = args[i + 1]
            text = open(raw[1:], encoding='utf-8').read() if raw.startswith('@') else raw
            payload = json.loads(text)
            i += 2
            continue
        raise SystemExit('unexpected argument for --bridge-action: %s' % args[i])
    payload['action'] = action
    res = bridge_call(payload, port=port)
    print(json.dumps(res, indent=2))
    return 0 if res.get('status') == 'ok' else 1


def bridge_run_script(args, port):
    if not args:
        raise SystemExit('--bridge needs a script.py path')
    script = os.path.abspath(args[0])
    if not os.path.isfile(script):
        raise SystemExit('no such script: ' + script)
    s2_env = {k: v for k, v in os.environ.items() if k.startswith('S2_')}
    start = time.time()
    res = bridge_call({'action': 'run_script', 'script': script, 'args': args[1:], 'env': s2_env}, port=port)
    if res.get('status') != 'ok':
        msg = res.get('traceback') or res.get('error') or str(res)
        if res.get('output'):
            print(res['output'].rstrip('\n'))
        print('bridge script failed: %s' % msg, file=sys.stderr)
        return 1
    out = (res.get('output') or '').rstrip('\n')
    if out:
        print(out)
    lines = out.splitlines() if out else []
    print('--- %.2f s, %d python lines, live bridge ---' % (time.time() - start, len(lines)))
    return 0


def main():
    args = sys.argv[1:]
    if not args or '-h' in args or '--help' in args:
        print(__doc__)
        return 0 if args else 2
    if args[0] in ('--bridge-status', '--bridge-action', '--bridge'):
        flag = args[0]
        port, rest = _pop_port(args[1:])
        if flag == '--bridge-status':
            return bridge_status(port=port)
        if flag == '--bridge-action':
            return bridge_action(rest, port=port)
        return bridge_run_script(rest, port=port)
    if os.name != 'nt':
        raise SystemExit('sdk_run.py runs the Windows Zone Kit editor; it needs Windows')
    if args[0] == '--wait':
        wait()
    elif args[0] == '--launch':
        if len(args) < 2:
            raise SystemExit('--launch needs a script')
        launch(args[1])
    else:
        wait(launch(args[0]))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except s2paths.S2PathError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
