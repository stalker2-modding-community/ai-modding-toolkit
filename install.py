#!/usr/bin/env python3
r"""STALKER 2 AI Modding Toolkit installer.

It copies skill folders from this pack into the folders your AI agents read. That is all it does: no network,
no admin rights, it never runs anything from the pack, and it never overwrites a skill it did not install
(unless you pass --replace-foreign, which backs that skill up first).

Interactive (a menu with descriptions):
  python install.py

For AI agents and scripts:
  python install.py --list [--json]                       skills, groups, token cost, and the agents found here
  python install.py --describe stalker2-paks              one skill's full description
  python install.py --install all|core|zonekit|<names or numbers> [--exclude <names or numbers>]
                    --agent <ids> [--scope user|project --project-dir DIR] [--dry-run] [--yes] [--replace-foreign]
                    (--exclude numbers refer to the full --list numbering, not positions within a preset)
  python install.py --uninstall all|<names> --agent <ids> [--scope ...] [--yes]
  python install.py --verify --agent <ids> [--scope ...]  check installed files against their recorded hashes
  python install.py --agents-md FILE --agent <id> [--remove]   add / remove a skill index block in an AGENTS.md
  python install.py --claude-ai                           how to upload skills to claude.ai / Claude Desktop

Agent ids: claude-code, agents (Codex, Copilot, Cursor, Gemini CLI, Windsurf, OpenCode, Goose, Amp, Junie),
kiro, cline, antigravity. Several at once: --agent claude-code,agents
Exit codes: 0 ok, 1 error, 2 bad usage, 3 something was refused (see the output).
"""
import datetime, hashlib, json, os, re, shutil, sys

PACK_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(PACK_DIR, 'skills')
MARKER = '.stalker2-skill-pack.json'          # inside each installed skill folder (never a manifest.json)
NAME_RX = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
BLOCK_START = '<!-- stalker2-skill-pack:start (managed by install.py, remove with: install.py --agents-md FILE --remove) -->'
BLOCK_END = '<!-- stalker2-skill-pack:end -->'

AGENTS = [
    ('claude-code', 'Claude Code (terminal, desktop app, IDE)', '.claude/skills', '.claude/skills', ['.claude']),
    ('agents', 'Shared .agents folder: Codex, GitHub Copilot, Cursor, Gemini CLI, Windsurf / Devin, OpenCode, Goose, Amp, Junie',
     '.agents/skills', '.agents/skills',
     ['.agents', '.codex', '.copilot', '.cursor', '.gemini', '.codeium', '.config/opencode', '.config/goose', '.config/amp', '.junie']),
    ('kiro', 'Kiro', '.kiro/skills', '.kiro/skills', ['.kiro']),
    ('cline', 'Cline', '.cline/skills', '.cline/skills', ['.cline']),
    ('antigravity', 'Google Antigravity IDE', '.gemini/config/skills', '.agents/skills', ['.gemini/config', '.gemini/antigravity']),
]
AGENT_IDS = [a[0] for a in AGENTS]


class Refused(Exception):
    pass


def say(msg=''):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', 'replace').decode('ascii'))


# ---------------- catalog ----------------

DEFAULT_GROUPS = [
    ('start', 'Start here', ['stalker2-workflow', 'stalker2-mod-setup', 'stalker2-updates', 'stalker2-linux']),
    ('data', 'Game files and data', ['stalker2-paks', 'stalker2-cfg', 'stalker2-gamedata', 'stalker2-curves',
                                     'stalker2-localization', 'stalker2-saves']),
    ('test', 'Testing and fixing', ['stalker2-testing', 'stalker2-crashes']),
    ('kit', 'Zone Kit and assets', ['stalker2-zonekit', 'stalker2-blueprints', 'stalker2-mod-menus', 'stalker2-animation',
                                    'stalker2-audio', 'stalker2-voiceover']),
    ('ship', 'Shipping mods', ['stalker2-release', 'stalker2-vortex', 'stalker2-publish']),
]
DEFAULT_PRESETS = {
    'core': ['stalker2-workflow', 'stalker2-mod-setup', 'stalker2-updates', 'stalker2-paks', 'stalker2-cfg', 'stalker2-gamedata',
             'stalker2-testing', 'stalker2-crashes', 'stalker2-release', 'stalker2-vortex'],
    'zonekit': ['stalker2-workflow', 'stalker2-mod-setup', 'stalker2-updates', 'stalker2-paks', 'stalker2-cfg',
                'stalker2-curves', 'stalker2-zonekit', 'stalker2-blueprints', 'stalker2-testing', 'stalker2-crashes',
                'stalker2-release', 'stalker2-vortex'],
}


def _unquote(v):
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
        return v[1:-1]
    return v


def _tok(chars):
    return int(round(chars / 4.0))


def _read_frontmatter(path):
    text = open(path, encoding='utf-8').read()
    out = {}
    if text.startswith('---'):
        end = text.find('\n---', 3)
        for line in text[3:end].splitlines():
            if line and not line.startswith(' ') and ':' in line:
                k, v = line.split(':', 1)
                out[k.strip()] = _unquote(v.strip())
    return out


def _estimate_tokens(skill_dir, fm):
    sk = os.path.join(skill_dir, 'SKILL.md')
    text = open(sk, encoding='utf-8').read()
    end = text.find('\n---', 3) if text.startswith('---') else -1
    body = text[end + 4:].lstrip('\n') if end >= 0 else text
    ref_dir = os.path.join(skill_dir, 'references')
    ref_chars = 0
    if os.path.isdir(ref_dir):
        for fn in os.listdir(ref_dir):
            fp = os.path.join(ref_dir, fn)
            if os.path.isfile(fp):
                ref_chars += len(open(fp, encoding='utf-8').read())
    return {
        'listing': _tok(len(fm.get('name', '')) + len(fm.get('description', ''))),
        'body': _tok(len(body)),
        'references': _tok(ref_chars),
    }


def load_catalog():
    p = os.path.join(PACK_DIR, 'catalog.json')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    # fallback when run from an unbuilt source folder: read the skills directly
    group_of = {n: gid for gid, _, ns in DEFAULT_GROUPS for n in ns}
    skills = []
    for n in sorted(os.listdir(SKILLS_DIR)):
        sdir = os.path.join(SKILLS_DIR, n)
        sk = os.path.join(sdir, 'SKILL.md')
        if os.path.isfile(sk):
            fm = _read_frontmatter(sk)
            desc = fm.get('description', '')
            skills.append({'name': n, 'group': group_of.get(n, 'other'), 'description': desc,
                           'requires': fm.get('compatibility', ''), 'tokens': _estimate_tokens(sdir, fm), 'files': []})
    present = {s['name'] for s in skills}
    groups = [{'id': gid, 'title': title, 'skills': [n for n in ns if n in present]}
              for gid, title, ns in DEFAULT_GROUPS]
    extras = [s['name'] for s in skills if s['name'] not in group_of]
    if extras:
        groups.append({'id': 'other', 'title': 'Other', 'skills': extras})
    version = open(os.path.join(PACK_DIR, 'VERSION'), encoding='utf-8').read().strip() \
        if os.path.isfile(os.path.join(PACK_DIR, 'VERSION')) else '?'
    return {'pack': 'STALKER 2 AI Modding Toolkit', 'id': 'STALKER2-AI-Modding-Toolkit', 'version': version,
            'groups': [g for g in groups if g['skills']], 'presets': DEFAULT_PRESETS, 'skills': skills}


def ordered_skills(cat):
    by = {s['name']: s for s in cat['skills']}
    out = []
    for g in cat['groups']:
        for n in g['skills']:
            if n in by:
                out.append(by[n])
    return out


def short(desc, width=88):
    first = re.split(r'(?<=[.!?])\s', desc, maxsplit=1)[0]
    return first if len(first) <= width else first[:width - 3].rstrip() + '...'


def tok(s):
    t = s.get('tokens') or {}
    if not t:
        return ''
    return '~%.1fk' % (t.get('body', 0) / 1000.0)


# ---------------- targets ----------------

def home_dir(args):
    return os.path.abspath(args.get('home') or os.path.expanduser('~'))


def detect_agents(home):
    found = []
    for aid, title, _, _, probes in AGENTS:
        if any(os.path.isdir(os.path.join(home, p)) for p in probes):
            found.append(aid)
    return found


def target_dirs(agent_ids, scope, home, project_dir):
    out, seen = [], set()
    for aid, title, upath, ppath, _ in AGENTS:
        if aid not in agent_ids:
            continue
        base = home if scope == 'user' else project_dir
        d = os.path.normpath(os.path.join(base, upath if scope == 'user' else ppath))
        if d.lower() not in seen:
            seen.add(d.lower())
            out.append((aid, d))
    return out


def state_dir(home):
    return os.path.join(home, '.stalker2-skill-pack')


# ---------------- file helpers ----------------

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def pack_files(name):
    """Regular files of one skill in the pack (relative path -> absolute). Symlinks and odd names are refused."""
    root = os.path.join(SKILLS_DIR, name)
    real_root = os.path.realpath(root)
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('__pycache__', 'node_modules', '.git')]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if os.path.islink(p) or not os.path.isfile(p):
                raise Refused('%s: %s is not a regular file' % (name, p))
            if not os.path.realpath(p).startswith(real_root + os.sep):
                raise Refused('%s: %s points outside the skill' % (name, p))
            rel = os.path.relpath(p, root).replace('\\', '/')
            if rel.startswith('../') or rel == MARKER:
                raise Refused('%s: bad file name %s' % (name, rel))
            files[rel] = p
    if 'SKILL.md' not in files:
        raise Refused('%s: no SKILL.md in the pack' % name)
    return files


def read_marker(d):
    try:
        with open(os.path.join(d, MARKER), encoding='utf-8') as f:
            m = json.load(f)
        return m if isinstance(m, dict) else None
    except (OSError, ValueError):
        return None


def folder_matches_marker(d, marker):
    """True when the folder holds exactly the files we installed, unchanged."""
    listed = marker.get('files', {})
    for dirpath, _, filenames in os.walk(d):
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), d).replace('\\', '/')
            if rel == MARKER:
                continue
            if rel not in listed or sha256(os.path.join(dirpath, fn)) != listed[rel]:
                return False
    return all(os.path.isfile(os.path.join(d, r)) for r in listed)


def backup(d, home, aid, stamp, dry):
    dest = os.path.join(state_dir(home), 'backups', stamp, aid, os.path.basename(d))
    if not dry:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(d, dest)
    return dest


# ---------------- actions ----------------

def install_one(cat, name, aid, tdir, home, stamp, opts):
    dry, replace_foreign = opts['dry'], opts['replace_foreign']
    if not NAME_RX.match(name):
        raise Refused('bad skill name %r' % name)
    files = pack_files(name)
    expected = {f['path']: f['sha256'] for s in cat['skills'] if s['name'] == name for f in s.get('files', [])}
    dst = os.path.join(tdir, name)
    note = 'new'
    if os.path.lexists(dst):
        if os.path.islink(dst) or not os.path.isdir(dst):
            raise Refused('%s exists and is not a plain folder; left alone' % dst)
        marker = read_marker(dst)
        if marker and marker.get('pack') == cat['id']:
            if folder_matches_marker(dst, marker):
                note = 'update (was %s)' % marker.get('version', '?')
            else:
                b = backup(dst, home, aid, stamp, dry)
                note = 'update; you had changed files, old folder backed up to %s' % b
        elif replace_foreign:
            b = backup(dst, home, aid, stamp, dry)
            note = 'replaced a skill this pack did not install; backed up to %s' % b
        else:
            raise Refused('%s already exists and was not installed by this pack (your own copy?). Left alone. '
                          'Use --replace-foreign to back it up and replace it, or install with --scope project instead.' % dst)
    say('  %-8s %-24s -> %s  (%s)' % ('[dry]' if dry else 'install', name, dst, note))
    if dry:
        return
    tmp = os.path.join(tdir, '.%s.installing' % name)       # build the new copy aside, swap it in at the end
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    hashes = {}
    try:
        for rel, src in sorted(files.items()):
            t = os.path.join(tmp, *rel.split('/'))
            os.makedirs(os.path.dirname(t), exist_ok=True)
            shutil.copyfile(src, t)
            hashes[rel] = sha256(t)
            if expected and expected.get(rel) not in (None, hashes[rel]):
                raise Refused('%s/%s does not match the pack checksum; the pack may be damaged or changed. Nothing installed.'
                              % (name, rel))
        with open(os.path.join(tmp, MARKER), 'w', encoding='utf-8') as f:
            json.dump({'pack': cat['id'], 'version': cat['version'], 'skill': name, 'agent': aid,
                       'installed': datetime.datetime.now().isoformat(timespec='seconds'), 'files': hashes}, f, indent=2)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.replace(tmp, dst)


def uninstall_one(cat, name, aid, tdir, home, stamp, opts):
    dst = os.path.join(tdir, name)
    if not os.path.isdir(dst):
        return False
    marker = read_marker(dst)
    if not marker or marker.get('pack') != cat['id']:
        raise Refused('%s was not installed by this pack; left alone' % dst)
    note = 'removed'
    if not folder_matches_marker(dst, marker):
        b = backup(dst, home, aid, stamp, opts['dry'])
        note = 'removed; it had changed files, backed up to %s' % b
    say('  %-8s %-24s %s  (%s)' % ('[dry]' if opts['dry'] else 'remove', name, dst, note))
    if not opts['dry']:
        shutil.rmtree(dst)
    return True


def verify(cat, names, targets):
    bad = 0
    for aid, tdir in targets:
        for n in names:
            d = os.path.join(tdir, n)
            if not os.path.isdir(d):
                continue
            m = read_marker(d)
            if not m or m.get('pack') != cat['id']:
                say('  not ours  %s' % d)
                continue
            ok = folder_matches_marker(d, m)
            bad += 0 if ok else 1
            say('  %-9s %s (version %s)' % ('ok' if ok else 'CHANGED', d, m.get('version')))
    return bad


def agents_md(cat, path, aid, home, args, remove=False):
    path = os.path.abspath(path)
    text = open(path, encoding='utf-8').read() if os.path.isfile(path) else ''
    text = re.sub(r'\n?' + re.escape(BLOCK_START) + r'.*?' + re.escape(BLOCK_END) + r'\n?', '\n', text, flags=re.S).rstrip() + '\n'
    st_path = os.path.join(state_dir(home), 'state.json')
    try:
        st = json.load(open(st_path, encoding='utf-8'))
    except (OSError, ValueError):
        st = {}
    files = set(st.get('agents_md', []))
    if remove:
        files.discard(path)
        say('  removed the skill index block from %s' % path)
    else:
        scope = args.get('scope', 'user')
        tdir = target_dirs([aid], scope, home, args.get('project_dir') or os.getcwd())[0][1]
        lines = [BLOCK_START, '## STALKER 2 modding skills',
                 'When a task matches one of these skills, read its SKILL.md first and follow it.']
        for s in ordered_skills(cat):
            sk = os.path.join(tdir, s['name'], 'SKILL.md')
            if os.path.isfile(sk):
                lines.append('- %s: %s (%s)' % (s['name'], short(s['description'], 160), sk.replace('\\', '/')))
        if len(lines) == 3:
            say('  no skills from this pack are installed for %s yet; install first' % aid)
            return 1
        lines.append(BLOCK_END)
        text = (text.rstrip() + '\n\n' if text.strip() else '') + '\n'.join(lines) + '\n'
        files.add(path)
        say('  wrote a skill index block (%d skills) into %s' % (len(lines) - 4, path))
    if not args.get('dry_run'):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        st['agents_md'] = sorted(files)
        os.makedirs(state_dir(home), exist_ok=True)
        json.dump(st, open(st_path, 'w', encoding='utf-8'), indent=2)
    return 0


def remove_all_blocks(cat, home, dry):
    st_path = os.path.join(state_dir(home), 'state.json')
    try:
        st = json.load(open(st_path, encoding='utf-8'))
    except (OSError, ValueError):
        return
    for p in st.get('agents_md', []):
        if os.path.isfile(p):
            agents_md(cat, p, 'agents', home, {'dry_run': dry}, remove=True)


CLAUDE_AI_HELP = """Uploading skills to claude.ai or Claude Desktop (labels can differ a little between app versions):
  1. Open claude.ai (or the Claude desktop app) and sign in.
  2. Open Settings, then the Capabilities (or Customize) page, and make sure code execution is turned on.
  3. Find the Skills section and click "Upload skill" (or "Add skill").
  4. Pick one zip from this pack's claude-ai folder, for example claude-ai/stalker2-paks.zip, and confirm.
  5. Repeat for each skill you want. Each zip holds one skill folder with its SKILL.md at the top.
Notes: skills uploaded there are separate from Claude Code's; scripts that need Windows tools (retoc, repak,
the Zone Kit) only work where those tools exist, so on claude.ai use the skills for their knowledge."""


# ---------------- selection ----------------

def resolve_selection(cat, sel):
    order = [s['name'] for s in ordered_skills(cat)]
    sel = (sel or '').strip()
    if sel in ('all', 'a'):
        return order
    if sel in cat.get('presets', {}):
        return [n for n in order if n in cat['presets'][sel]]
    if sel in ('core', 'c') and 'core' in cat.get('presets', {}):
        return [n for n in order if n in cat['presets']['core']]
    picked = []
    for part in re.split(r'[,\s]+', sel):
        if not part:
            continue
        m = re.match(r'^(\d+)-(\d+)$', part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            idx = range(min(a, b), max(a, b) + 1)
        elif part.isdigit():
            idx = [int(part)]
        else:
            if part not in order:
                raise ValueError('unknown skill %r' % part)
            idx = [order.index(part) + 1]
        for i in idx:
            if not 1 <= i <= len(order):
                raise ValueError('no skill number %d' % i)
            if order[i - 1] not in picked:
                picked.append(order[i - 1])
    return [n for n in order if n in picked]


def resolve_agents(sel, found):
    sel = (sel or '').strip()
    if not sel:
        raise ValueError('choose at least one agent')
    out = []
    for part in re.split(r'[,\s]+', sel):
        if not part:
            continue
        if part.isdigit():
            i = int(part)
            if not 1 <= i <= len(AGENTS):
                raise ValueError('no agent number %d' % i)
            part = AGENTS[i - 1][0]
        if part not in AGENT_IDS:
            raise ValueError('unknown agent %r (use: %s)' % (part, ', '.join(AGENT_IDS)))
        if part not in out:
            out.append(part)
    return out


# ---------------- listing ----------------

def print_list(cat, home, as_json):
    found = detect_agents(home)
    if as_json:
        print(json.dumps({'pack': cat['pack'], 'version': cat['version'], 'verified_on': cat.get('verified_on', ''),
                          'presets': cat.get('presets', {}),
                          'skills': [{'number': i + 1, 'name': s['name'], 'group': s['group'], 'description': s['description'],
                                      'requires': s.get('requires', ''), 'tokens': s.get('tokens', {})}
                                     for i, s in enumerate(ordered_skills(cat))],
                          'agents': [{'id': a[0], 'title': a[1], 'user_path': '~/' + a[2], 'project_path': a[3],
                                      'found_on_this_pc': a[0] in found} for a in AGENTS]}, indent=2))
        return
    say('%s %s  (a community project)' % (cat['pack'], cat['version']))
    if cat.get('verified_on'):
        say('Facts verified on: %s' % cat['verified_on'])
    i = 0
    by = {s['name']: s for s in cat['skills']}
    for g in cat['groups']:
        say('\n  %s' % g['title'])
        for n in g['skills']:
            if n not in by:
                continue
            i += 1
            s = by[n]
            say('  %2d  %-22s %5s  %s' % (i, n, tok(s), short(s['description'])))
    for pname, pskills in (cat.get('presets') or {}).items():
        say('\n  %-7s = %s' % (pname, ', '.join(pskills)))
    say('\n  Token column: the cost when the agent opens that skill. Until then each skill costs ~100 tokens.')
    say('  Tip: pass --exclude <names or numbers> with --install to skip skills you do not need.')
    say('\nAgents')
    for j, a in enumerate(AGENTS, 1):
        say('  %d  %-12s %-6s %s' % (j, a[0], 'found' if a[0] in found else '', a[1]))


# ---------------- run ----------------

def run_actions(cat, names, agent_ids, args, home, mode):
    scope = args.get('scope', 'user')
    project_dir = os.path.abspath(args.get('project_dir') or os.getcwd())
    if scope == 'project' and not args.get('project_dir'):
        say('Project scope: installing into %s (pass --project-dir to choose another folder).' % project_dir)
    targets = target_dirs(agent_ids, scope, home, project_dir)
    if mode == 'verify':
        return 1 if verify(cat, names, targets) else 0
    opts = {'dry': bool(args.get('dry_run')), 'replace_foreign': bool(args.get('replace_foreign'))}
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    refused = 0
    for aid, tdir in targets:
        say('%s -> %s' % (aid, tdir))
        if mode == 'install' and not opts['dry']:
            os.makedirs(tdir, exist_ok=True)
        for n in names:
            try:
                if mode == 'install':
                    install_one(cat, n, aid, tdir, home, stamp, opts)
                else:
                    uninstall_one(cat, n, aid, tdir, home, stamp, opts)
            except Refused as e:
                refused += 1
                say('  REFUSED  %s' % e)
    if mode == 'uninstall' and set(names) == {s['name'] for s in cat['skills']}:
        remove_all_blocks(cat, home, opts['dry'])
    if mode == 'install' and not opts['dry']:
        say('\nDone. Restart your agent (or start a new session) so it sees the skills.')
        say('Scripts in the skills find the game and the Zone Kit by themselves; check with:')
        say('  python "%s"' % os.path.join(targets[0][1], 'stalker2-updates', 'scripts', 's2paths.py').replace('\\', '/')
            if targets and 'stalker2-updates' in names else '  python <skill>/scripts/s2paths.py')
        say('Tools you get yourself (retoc, repak, Oodle, Python packages): see START_HERE.md.')
        if 'stalker2-mod-setup' in names:
            say('Next: ask your agent to "learn my mod". It reads your mod (or your notes) and keeps a local repo for it.')
    return 3 if refused else 0


def ask(prompt, default=''):
    try:
        v = input(prompt).strip()
    except EOFError:
        return default
    return v or default


def interactive(cat, home):
    print_list(cat, home, False)
    say('\nThis installer only copies skill folders. It does not run anything from the pack or use the network.')
    while True:
        sel = ask('\nPick skills: a = all, c = core, or numbers like 1,3,5-7 (q to quit): ')
        if sel.lower() in ('q', 'quit', ''):
            return 0
        try:
            names = resolve_selection(cat, sel.lower() if sel.lower() in ('a', 'c', 'all', 'core') else sel)
            break
        except ValueError as e:
            say('  %s' % e)
    found = detect_agents(home)
    default = ','.join(str(AGENT_IDS.index(a) + 1) for a in found) or '1'
    while True:
        sel = ask('Install for which agents? numbers from the Agents list [%s]: ' % default, default)
        try:
            agent_ids = resolve_agents(sel, found)
            break
        except ValueError as e:
            say('  %s' % e)
    scope = ask('Install for [u]ser (every project) or [p]roject (one folder)? [u]: ', 'u').lower()
    args = {'scope': 'project' if scope.startswith('p') else 'user'}
    if args['scope'] == 'project':
        args['project_dir'] = ask('Project folder [%s]: ' % os.getcwd(), os.getcwd())
    say('\nPlan (nothing has been changed yet):')
    run_actions(cat, names, agent_ids, dict(args, dry_run=True), home, 'install')
    if ask('\nGo ahead? [y/N]: ', 'n').lower() not in ('y', 'yes'):
        say('Nothing was changed.')
        return 0
    return run_actions(cat, names, agent_ids, args, home, 'install')


def parse_args(argv):
    args, i = {}, 0
    flags = {'--json', '--dry-run', '--yes', '--replace-foreign', '--remove', '--claude-ai', '--list', '--verify', '--version', '-h', '--help'}
    valued = {'--install', '--exclude', '--uninstall', '--agent', '--scope', '--project-dir', '--describe', '--agents-md', '--home'}
    while i < len(argv):
        a = argv[i]
        if a in flags:
            args[a.lstrip('-').replace('-', '_')] = True
            i += 1
        elif a in valued:
            if i + 1 >= len(argv):
                raise ValueError('%s needs a value' % a)
            args[a.lstrip('-').replace('-', '_')] = argv[i + 1]
            i += 2
        else:
            raise ValueError('unknown argument %r (see --help)' % a)
    if args.get('scope') not in (None, 'user', 'project'):
        raise ValueError('--scope is user or project')
    return args


def main(argv):
    try:
        args = parse_args(argv)
    except ValueError as e:
        say(str(e))
        return 2
    if args.get('h') or args.get('help'):
        say(__doc__)
        return 0
    cat = load_catalog()
    home = home_dir(args)
    if args.get('version'):
        say('%s %s' % (cat['pack'], cat['version']))
        return 0
    if args.get('claude_ai'):
        say(CLAUDE_AI_HELP)
        return 0
    if args.get('list'):
        print_list(cat, home, bool(args.get('json')))
        return 0
    if args.get('describe'):
        for s in cat['skills']:
            if s['name'] == args['describe']:
                say('%s\n%s\nRequires: %s' % (s['name'], s['description'], s.get('requires') or 'nothing extra'))
                return 0
        say('unknown skill %r' % args['describe'])
        return 2
    try:
        if args.get('agents_md'):
            aid = resolve_agents(args.get('agent', 'agents'), [])[0]
            return agents_md(cat, args['agents_md'], aid, home, args, remove=bool(args.get('remove')))
        if args.get('exclude') and 'install' not in args:
            raise ValueError('--exclude only applies to --install')
        for mode in ('install', 'uninstall', 'verify'):
            if mode in args:
                sel = args.get(mode) if mode != 'verify' else 'all'
                names = resolve_selection(cat, sel)
                if mode == 'install' and args.get('exclude'):
                    excluded = set(resolve_selection(cat, args['exclude']))
                    ignored = sorted(excluded - set(names))
                    if ignored and not args.get('json'):
                        say('note: --exclude ignored skill(s) not in selection: ' + ', '.join(ignored))
                    names = [n for n in names if n not in excluded]
                    if not names:
                        raise ValueError('no skills left after --exclude')
                agent_ids = resolve_agents(args.get('agent', ''), detect_agents(home))
                if mode != 'verify' and not args.get('yes') and not args.get('dry_run'):
                    run_actions(cat, names, agent_ids, dict(args, dry_run=True), home, mode)
                    if ask('\nGo ahead? [y/N]: ', 'n').lower() not in ('y', 'yes'):
                        say('Nothing was changed.')
                        return 0
                return run_actions(cat, names, agent_ids, args, home, mode)
    except ValueError as e:
        say(str(e))
        return 2
    except OSError as e:
        say('error: %s' % e)
        return 1
    if not sys.stdin or not sys.stdin.isatty():
        say(__doc__)
        return 2
    return interactive(cat, home)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
