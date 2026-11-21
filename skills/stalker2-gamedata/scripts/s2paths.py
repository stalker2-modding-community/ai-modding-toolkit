r"""Find the STALKER 2 game, the Zone Kit, ~mods and the modding tools for the pack's scripts.

Each path is looked up when a script first needs it, in this order:
  1. an environment variable (S2_GAME_DIR, S2_ZONEKIT_DIR, S2_MODS_DIR, S2_TOOLS_DIR, S2_WORK_DIR, S2_UASSET_DUMP)
  2. the pack's config file (see CONFIG_FILE below; written by `--write`)
  3. auto-detection (Steam library folders for the game; walking up from the script and working folders then Epic launcher manifests for the Zone Kit; PATH for tools)
If nothing is found the script stops with a message that says how to fix it.

  python s2paths.py            table of every path and where it came from
  python s2paths.py --json     the same as JSON
  python s2paths.py --write    save the detected paths to the config file (only paths that were found)
  python s2paths.py --set game="<folder>"   set one path by hand (keys: game kit mods tools work uasset_dump)

Read-only: detection only reads the registry, Steam and Epic manifest files; it never changes them.
"""
import glob, json, os, re, shutil, sys

STEAM_APP_ID = '1643320'
_HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = ('game', 'kit', 'mods', 'tools', 'work', 'uasset_dump')
ENV = {'game': 'S2_GAME_DIR', 'kit': 'S2_ZONEKIT_DIR', 'mods': 'S2_MODS_DIR', 'tools': 'S2_TOOLS_DIR',
       'work': 'S2_WORK_DIR', 'uasset_dump': 'S2_UASSET_DUMP'}
HINT = {
    'game': 'the STALKER 2 install folder (the one holding Stalker2.exe)',
    'kit': 'the STALKER 2 Zone Kit install folder (the one holding Stalker2/Stalker2.uproject)',
    'mods': '<game>/Stalker2/Content/Paks/~mods',
    'tools': 'a folder holding retoc.exe and repak.exe (and oo2core_9_win64.dll next to them)',
    'work': 'a scratch folder for temporary files',
    'uasset_dump': 'uasset-dump.exe, built from the stalker2-zonekit skill (tools/uasset-dump, `dotnet build -c Release`)',
}


class S2PathError(RuntimeError):
    pass


def _config_dir():
    if os.name == 'nt':
        return os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'stalker2-skill-pack')
    return os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config'), 'stalker2-skill-pack')


CONFIG_FILE = os.path.join(_config_dir(), 'paths.json')


def _load_config():
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# ---------- auto-detection ----------

def _steam_roots():
    roots = []
    if os.name == 'nt':
        try:
            import winreg
            for hive, key, value in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                     (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        roots.append(os.path.normpath(winreg.QueryValueEx(k, value)[0]))
                except OSError:
                    pass
        except ImportError:
            pass
    for p in ('~/.steam/steam', '~/.local/share/Steam', '~/Library/Application Support/Steam'):
        roots.append(os.path.expanduser(p))
    seen, out = set(), []
    for r in roots:
        if r and os.path.isdir(r) and r.lower() not in seen:
            seen.add(r.lower())
            out.append(r)
    return out


def _steam_libraries():
    libs = []
    for root in _steam_roots():
        libs.append(root)
        vdf = os.path.join(root, 'steamapps', 'libraryfolders.vdf')
        try:
            text = open(vdf, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            libs.append(os.path.normpath(m.group(1).replace('\\\\', '\\')))
    seen, out = set(), []
    for lib in libs:
        if lib.lower() not in seen and os.path.isdir(lib):
            seen.add(lib.lower())
            out.append(lib)
    return out


def steam_manifest():
    """Path of the game's Steam appmanifest_1643320.acf, or None (GOG / Game Pass / not found)."""
    game = get('game', required=False)
    for lib in _steam_libraries():
        acf = os.path.join(lib, 'steamapps', 'appmanifest_%s.acf' % STEAM_APP_ID)
        if os.path.isfile(acf):
            if not game:
                return acf
            if os.path.normcase(os.path.abspath(game)).startswith(os.path.normcase(os.path.abspath(lib))):
                return acf
    if game:   # the manifest normally sits two levels above steamapps/common/<game>
        acf = os.path.join(os.path.dirname(os.path.dirname(game)), 'appmanifest_%s.acf' % STEAM_APP_ID)
        if os.path.isfile(acf):
            return acf
    return None


def _detect_game():
    for lib in _steam_libraries():
        acf = os.path.join(lib, 'steamapps', 'appmanifest_%s.acf' % STEAM_APP_ID)
        if not os.path.isfile(acf):
            continue
        m = re.search(r'"installdir"\s+"([^"]+)"', open(acf, encoding='utf-8', errors='replace').read())
        if m:
            d = os.path.join(lib, 'steamapps', 'common', m.group(1))
            if os.path.isdir(os.path.join(d, 'Stalker2', 'Content', 'Paks')):
                return d
    return None


def _detect_kit():
    seen = set()
    for start in (os.path.abspath(_HERE), os.getcwd()):
        cur = os.path.abspath(start)
        while True:
            key = os.path.normcase(cur)
            if key in seen:
                break
            seen.add(key)
            if os.path.isfile(os.path.join(cur, 'Stalker2', 'Stalker2.uproject')):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    base = os.environ.get('PROGRAMDATA') or os.environ.get('ALLUSERSPROFILE')
    if not base:
        return None
    for item in glob.glob(os.path.join(base, 'Epic', 'EpicGamesLauncher', 'Data', 'Manifests', '*.item')):
        try:
            data = json.load(open(item, encoding='utf-8', errors='replace'))
        except (OSError, ValueError):
            continue
        exe = str(data.get('LaunchExecutable', ''))
        name = str(data.get('DisplayName', ''))
        if exe.lower().endswith('stalker2modeditor.exe') or 'zone kit' in name.lower():
            loc = data.get('InstallLocation')
            if loc and os.path.isfile(os.path.join(loc, 'Stalker2', 'Stalker2.uproject')):
                return os.path.normpath(loc)
    return None


def _detect_tools():
    for exe in ('retoc', 'repak'):
        p = shutil.which(exe)
        if p:
            return os.path.dirname(p)
    return None


def _detect_uasset_dump():
    skills = os.path.dirname(os.path.dirname(_HERE))          # <skills>/<this skill>/scripts -> <skills>
    for root in (os.path.dirname(_HERE), os.path.join(skills, 'stalker2-zonekit')):
        for cfg in ('Release', 'Debug'):
            p = os.path.join(root, 'tools', 'uasset-dump', 'bin', cfg, 'net8.0', 'uasset-dump.exe')
            if os.path.isfile(p):
                return p
    return shutil.which('uasset-dump')


def _detect(key):
    if key == 'game':
        return _detect_game()
    if key == 'kit':
        return _detect_kit()
    if key == 'mods':
        g = get('game', required=False)
        return os.path.join(g, 'Stalker2', 'Content', 'Paks', '~mods') if g else None
    if key == 'tools':
        return _detect_tools()
    if key == 'work':
        base = os.environ.get('LOCALAPPDATA') if os.name == 'nt' else None
        base = base or os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache')
        return os.path.join(base, 'stalker2-skill-pack', 'work')
    if key == 'uasset_dump':
        return _detect_uasset_dump()
    raise KeyError(key)


# ---------- lookup ----------

def lookup(key):
    """(value, source) where source is 'env', 'config', 'detected' or 'missing'."""
    if key not in KEYS:
        raise KeyError(key)
    v = os.environ.get(ENV[key])
    if v:
        return os.path.normpath(v), 'env'
    v = _load_config().get(key)
    if v:
        return os.path.normpath(v), 'config'
    v = _detect(key)
    return (os.path.normpath(v), 'detected') if v else (None, 'missing')


def get(key, required=True):
    v, _ = lookup(key)
    if v is None and required:
        raise S2PathError('Cannot find %s (%s).\nSet it once with:  python "%s" --set %s="<path>"\n'
                          'or set the environment variable %s.' % (key, HINT[key], os.path.abspath(__file__), key, ENV[key]))
    return v


def game_dir():
    return get('game')


def paks_dir():
    return os.path.join(game_dir(), 'Stalker2', 'Content', 'Paks')


def mods_dir():
    return get('mods')


def kit_dir():
    return get('kit')


def kit_gamedata():
    """The Zone Kit's commented TEXT cfg tree."""
    return os.path.join(kit_dir(), 'Stalker2', 'Content', 'GameLite', 'GameData')


def kit_editor_pak():
    """The Zone Kit pak with GSC's uncooked assets and the editor's localization."""
    return os.path.join(kit_dir(), 'Stalker2', 'Content', 'Paks', 'FullEditor-WindowsModEditor.pak')


def work_dir():
    d = get('work')
    os.makedirs(d, exist_ok=True)
    return d


def tool(name):
    """Full path of retoc or repak: S2_TOOLS_DIR / config 'tools', then PATH."""
    exe = name + ('.exe' if os.name == 'nt' else '')
    d = get('tools', required=False)
    if d:
        for p in (os.path.join(d, exe), os.path.join(d, name, exe)):
            if os.path.isfile(p):
                return p
    p = shutil.which(name)
    if p:
        return p
    raise S2PathError('Cannot find %s. Download it (see the pack START_HERE.md, "Tools you get yourself"), put it in a folder '
                      'with oo2core_9_win64.dll, then:  python "%s" --set tools="<that folder>"' % (exe, os.path.abspath(__file__)))


def uasset_dump():
    return get('uasset_dump')


# ---------- command line ----------

def _write(updates):
    data = _load_config()
    data.update(updates)
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    tmp = CONFIG_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CONFIG_FILE)


def main(argv):
    if '-h' in argv or '--help' in argv:
        print(__doc__)
        return 0
    if '--set' in argv:
        i = argv.index('--set')
        if i + 1 >= len(argv) or '=' not in argv[i + 1]:
            print('usage: --set key="<path>"  (keys: %s)' % ' '.join(KEYS))
            return 2
        key, val = argv[i + 1].split('=', 1)
        key, val = key.strip(), val.strip().strip('"')
        if key not in KEYS:
            print('unknown key %r (keys: %s)' % (key, ' '.join(KEYS)))
            return 2
        if not os.path.exists(val):
            print('warning: %s does not exist (saved anyway)' % val)
        _write({key: os.path.normpath(val)})
        print('saved %s in %s' % (key, CONFIG_FILE))
        return 0
    rows = {k: lookup(k) for k in KEYS}
    acf = steam_manifest()
    if '--write' in argv:
        found = {k: v for k, (v, src) in rows.items() if src == 'detected' and k != 'work'}
        _write(found)
        print('saved %d path(s) to %s' % (len(found), CONFIG_FILE))
    if '--json' in argv:
        print(json.dumps({'config_file': CONFIG_FILE, 'steam_manifest': acf,
                          'paths': {k: {'value': v, 'source': s} for k, (v, s) in rows.items()}}, indent=2))
        return 0
    print('config file: %s' % CONFIG_FILE)
    for k, (v, s) in rows.items():
        print('  %-12s %-9s %s' % (k, s.upper() if s == 'missing' else s, v or '-  (' + HINT[k] + ')'))
    print('  %-12s %-9s %s' % ('steam acf', 'detected' if acf else 'MISSING', acf or '-  (not a Steam install, or not found)'))
    for t in ('retoc', 'repak'):
        try:
            print('  %-12s %-9s %s' % (t, 'ok', tool(t)))
        except S2PathError:
            print('  %-12s %-9s %s' % (t, 'MISSING', '-  (' + HINT['tools'] + ')'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
