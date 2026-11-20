r"""Check, build and test the STALKER 2 AI Modding Toolkit.

  python -I tools/build_pack.py scan     [--only a,b]   scan of the repo (e-mail addresses, machine paths, secrets, dashes)
  python -I tools/build_pack.py validate [--only a,b]   Agent Skills spec + size + reference/script checks
  python -I tools/build_pack.py sync                    copy shared/s2paths.py into every skill whose scripts import it
  python -I tools/build_pack.py build                   sync + validate + scan, then dist/<pack>/ , per-skill claude.ai zips, the zip
  python -I tools/build_pack.py test                    install / reinstall / refuse / uninstall round trip into a temp home
  python -I tools/build_pack.py tokens                  token table (descriptions always loaded, bodies on use, references on demand)
Exit code 1 on any FAIL.
"""
import ast, hashlib, json, os, re, shutil, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = HERE
SKILLS = os.path.join(SRC, 'skills')
SHARED = os.path.join(SRC, 'shared')
DIST = os.path.join(HERE, 'dist')
PACK_ID = 'STALKER2-AI-Modding-Toolkit'
ZIP_DATE = (2026, 11, 15, 0, 0, 0)

TEXT_EXT = {'.md', '.py', '.mjs', '.js', '.json', '.txt', '.cs', '.csproj', '.bat', '.cmd', '.ps1', '.yaml', '.yml', '.ini'}
SKIP_DIRS = {'__pycache__', '.git', 'bin', 'obj', 'node_modules', '.vs', '.idea'}

if SRC not in sys.path:
    sys.path.insert(0, SRC)
from install import DEFAULT_GROUPS as GROUPS, DEFAULT_PRESETS as PRESETS

# ---------------- generic scan ----------------
ALLOWED_PHRASES = []
FAIL_RULES = [
    ('email', r'[\w.+-]+@[\w-]+\.[A-Za-z]{2,}'),
    ('path', r'(?<![A-Za-z0-9_])[A-Za-z]:[\\/]'),
    ('path', r'(?i)[\\/]Users[\\/]|/home/\w+'),
    ('secret', r'ghp_[A-Za-z0-9]{10,}|gho_[A-Za-z0-9]{10,}|github_pat_|\bsk-[A-Za-z0-9]{20,}|xox[abp]-|AKIA[0-9A-Z]{16}|'
               r'BEGIN [A-Z ]*PRIVATE KEY|Bearer [A-Za-z0-9._-]{20,}'),
    ('steam id', r'\b7656119\d{10}\b'),
    ('dash', '\u2014|\u2013'),
]
WARN_RULES = [
    ('download and run', r'(?i)invoke-webrequest|downloadstring|curl .*\| *(sh|bash)|\biex\b'),
    ('date', r'\b20\d\d-\d\d-\d\d\b'),
]
CREDIT_FILES = {'CREDITS.md'}          # other authors may be named here


def _iter_files(root, only=None):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (dirpath == root and d in ('tools', 'dist', '.github'))]
        rel = os.path.relpath(dirpath, SRC).replace('\\', '/')
        if only and rel.startswith('skills/'):
            parts = rel.split('/')
            if len(parts) >= 2 and parts[1] not in only:
                continue
        if only and rel in ('.', 'shared'):
            continue
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def scan(only=None, quiet=False):
    fails = warns = 0
    for path in _iter_files(SRC, only):
        rel = os.path.relpath(path, SRC).replace('\\', '/')
        ext = os.path.splitext(path)[1].lower()
        if ext not in TEXT_EXT and os.path.basename(path) not in ('VERSION', 'LICENSE', '.gitignore', '.gitattributes'):
            print('FAIL %s: file type %s is not allowed in the pack' % (rel, ext or '(none)'))
            fails += 1
            continue
        try:
            text = open(path, encoding='utf-8').read()
        except UnicodeDecodeError:
            print('FAIL %s: not UTF-8 text' % rel)
            fails += 1
            continue
        clean = text
        for p in ALLOWED_PHRASES:
            clean = clean.replace(p, '')
        is_credit = os.path.basename(path) in CREDIT_FILES
        for n, line in enumerate(clean.splitlines(), 1):
            for kind, rx in FAIL_RULES:
                if is_credit and kind == 'other mod':
                    continue
                if kind == 'id-like token' and ext in ('.py', '.mjs', '.js', '.cs'):
                    continue
                for m in re.finditer(rx, line):
                    print('FAIL %s:%d [%s] %r in: %s' % (rel, n, kind, m.group(0), line.strip()[:140]))
                    fails += 1
            if not quiet:
                for kind, rx in WARN_RULES:
                    if kind == 'date' and os.path.basename(path) == 'CHANGELOG.md':
                        continue
                    for m in re.finditer(rx, line):
                        print('WARN %s:%d [%s] %r in: %s' % (rel, n, kind, m.group(0), line.strip()[:140]))
                        warns += 1
    print('scan: %d FAIL, %d WARN' % (fails, warns))
    return fails


# ---------------- validate ----------------
NAME_RX = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')


def parse_skill(skill_dir):
    """Return (frontmatter dict, body text). Minimal YAML: key: value, one nested level under metadata."""
    text = open(os.path.join(skill_dir, 'SKILL.md'), encoding='utf-8').read()
    if not text.startswith('---\n'):
        raise ValueError('SKILL.md must start with --- frontmatter')
    end = text.find('\n---', 4)
    if end < 0:
        raise ValueError('frontmatter is not closed with ---')
    fm, body = text[4:end], text[end + 4:].lstrip('\n')
    data, current = {}, None
    for line in fm.splitlines():
        _, sep0, raw = line.strip().partition(':')
        raw = raw.strip()
        if sep0 and raw and raw[0] not in '"\'' and (': ' in raw or ' #' in raw or raw[0] in '&*!|>%@`{[,'):
            raise ValueError('frontmatter value needs quotes (YAML): %r' % line.strip()[:80])
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line.startswith('  ') and current is not None:
            k, _, v = line.strip().partition(':')
            data[current][k.strip()] = _unquote(v.strip())
            continue
        k, sep, v = line.partition(':')
        if not sep:
            raise ValueError('bad frontmatter line: %r' % line)
        k, v = k.strip(), v.strip()
        if v == '':
            data[k] = {}
            current = k
        else:
            data[k] = _unquote(v)
            current = None
    return data, body


def _unquote(v):
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
        return v[1:-1]
    return v


def skill_names():
    return sorted(d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d))) if os.path.isdir(SKILLS) else []


def validate(only=None):
    fails = warns = 0

    def f(msg):
        nonlocal fails
        fails += 1
        print('FAIL ' + msg)

    def w(msg):
        nonlocal warns
        warns += 1
        print('WARN ' + msg)

    names = skill_names()
    grouped = [n for _, _, ns in GROUPS for n in ns]
    if not only:
        for n in names:
            if n not in grouped:
                f('%s is not in any installer group (build.py GROUPS)' % n)
        for n in grouped:
            if n not in names:
                w('%s is listed in GROUPS but has no folder yet' % n)
    shared = open(os.path.join(SHARED, 's2paths.py'), 'rb').read()
    for n in names:
        if only and n not in only:
            continue
        d = os.path.join(SKILLS, n)
        if not os.path.isfile(os.path.join(d, 'SKILL.md')):
            f('%s: no SKILL.md' % n)
            continue
        try:
            fm, body = parse_skill(d)
        except ValueError as e:
            f('%s: %s' % (n, e))
            continue
        name, desc = fm.get('name', ''), fm.get('description', '')
        if name != n:
            f('%s: name %r must match the folder name' % (n, name))
        if not NAME_RX.match(name) or len(name) > 64:
            f('%s: name breaks the spec (a-z 0-9 -, max 64)' % n)
        if 'claude' in name or 'anthropic' in name:
            f('%s: reserved word in name' % n)
        if not (1 <= len(desc) <= 1024):
            f('%s: description length %d (1..1024)' % (n, len(desc)))
        elif len(desc) > 500:
            w('%s: description %d chars (target <= 450)' % (n, len(desc)))
        elif len(desc) < 120:
            w('%s: description only %d chars (say what + when)' % (n, len(desc)))
        if re.search(r'<[a-zA-Z/][^>]*>', desc) and '<game>' not in desc:
            w('%s: description contains something that looks like an XML tag' % n)
        for k in ('license', 'metadata'):
            if k not in fm:
                f('%s: frontmatter lacks %s' % (n, k))
        md = fm.get('metadata') or {}
        for k in ('pack', 'pack-version', 'author', 'verified-on'):
            if k not in md:
                f('%s: metadata lacks %s' % (n, k))
        extra = set(fm) - {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
        if extra:
            f('%s: unknown frontmatter fields %s' % (n, sorted(extra)))
        lines = body.count('\n') + 1
        if len(body) > 9000:
            f('%s: SKILL.md body %d chars (max ~6,000; move detail to references/)' % (n, len(body)))
        elif len(body) > 6500:
            w('%s: SKILL.md body %d chars (target <= 6,000)' % (n, len(body)))
        if lines > 500:
            f('%s: body has %d lines (max 500)' % (n, lines))
        elif lines > 150:
            w('%s: body has %d lines (target <= 150)' % (n, lines))
        # references and scripts
        alltext = body
        refdir = os.path.join(d, 'references')
        refs = sorted(os.listdir(refdir)) if os.path.isdir(refdir) else []
        for r in refs:
            p = os.path.join(refdir, r)
            t = open(p, encoding='utf-8').read()
            alltext += '\n' + t
            if 'references/' + r not in body:
                w('%s: references/%s is never mentioned in SKILL.md' % (n, r))
            if len(t) > 25000:
                f('%s: references/%s is %d chars (split it)' % (n, r, len(t)))
            elif len(t) > 14000:
                w('%s: references/%s is %d chars (target <= 14,000)' % (n, r, len(t)))
            if t.count('\n') > 100 and not re.search(r'(?im)^#+\s*(contents|table of contents)', '\n'.join(t.splitlines()[:20])):
                w('%s: references/%s is over 100 lines without a Contents section at the top' % (n, r))
            if re.search(r'references/[\w.-]+\.md', t):
                w('%s: references/%s points to another reference (keep one level deep)' % (n, r))
        for m in set(re.findall(r'references/([\w.-]+\.md)', body)):
            if m not in refs:
                f('%s: SKILL.md mentions references/%s which does not exist' % (n, m))
        scr = os.path.join(d, 'scripts')
        scripts = []
        if os.path.isdir(scr):
            for dirpath, dirnames, filenames in os.walk(scr):
                dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
                for fn in filenames:
                    scripts.append(os.path.relpath(os.path.join(dirpath, fn), scr).replace('\\', '/'))
        for m in set(re.findall(r'scripts/([\w./-]+\.(?:json|mjs|js|py))\b', alltext)):
            if m in scripts:
                continue
            owners = [o for o in names if o != n and os.path.isfile(os.path.join(SKILLS, o, 'scripts', m))]
            if owners:
                w('%s: mentions scripts/%s, which lives in %s: make sure the text names that skill' % (n, m, ', '.join(owners)))
            else:
                f('%s: text mentions scripts/%s which does not exist' % (n, m))
        uses_paths = False
        for s in scripts:
            p = os.path.join(scr, s)
            if s.endswith('.py'):
                src = open(p, encoding='utf-8').read()
                try:
                    tree = ast.parse(src, p)
                except SyntaxError as e:
                    f('%s: scripts/%s does not parse: %s' % (n, s, e))
                    continue
                if not ast.get_docstring(tree):
                    w('%s: scripts/%s has no module docstring (usage)' % (n, s))
                if re.search(r'^\s*(from s2paths import|import s2paths)', src, re.M):
                    uses_paths = True
                if re.search(r'shell\s*=\s*True|os\.system\(|\beval\(|\bexec\(', src):
                    w('%s: scripts/%s uses shell=True / os.system / eval / exec' % (n, s))
                if re.search(r'^\s*assert\s', src, re.M):
                    w('%s: scripts/%s uses assert for checks (stripped by python -O)' % (n, s))
                if re.search(r'urllib|requests|http\.client|http\.server|socketserver|socket\b', src):
                    w('%s: scripts/%s may use the network' % (n, s))
            if s.endswith('.mjs') and shutil.which('node'):
                r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
                if r.returncode:
                    f('%s: scripts/%s fails node --check: %s' % (n, s, r.stderr.strip()[:200]))
        if uses_paths:
            p = os.path.join(scr, 's2paths.py')
            if not os.path.isfile(p):
                f('%s: scripts import s2paths but scripts/s2paths.py is missing (run build.py sync)' % n)
            elif open(p, 'rb').read() != shared:
                f('%s: scripts/s2paths.py differs from src/shared/s2paths.py (run build.py sync)' % n)
    print('validate: %d FAIL, %d WARN' % (fails, warns))
    return fails


def sync():
    shared = os.path.join(SHARED, 's2paths.py')
    for n in skill_names():
        scr = os.path.join(SKILLS, n, 'scripts')
        if not os.path.isdir(scr):
            continue
        need = any(re.search(r'^\s*(from s2paths import|import s2paths)', open(os.path.join(scr, fn), encoding='utf-8').read(), re.M)
                   for fn in os.listdir(scr) if fn.endswith('.py') and fn != 's2paths.py')
        if need:
            shutil.copyfile(shared, os.path.join(scr, 's2paths.py'))
            print('synced s2paths.py -> %s' % n)


# ---------------- tokens ----------------

def _tok(chars):
    return int(round(chars / 4.0))


def token_table():
    rows = []
    for n in skill_names():
        d = os.path.join(SKILLS, n)
        try:
            fm, body = parse_skill(d)
        except (ValueError, OSError):
            continue
        refdir = os.path.join(d, 'references')
        ref_chars = sum(len(open(os.path.join(refdir, r), encoding='utf-8').read()) for r in os.listdir(refdir)) \
            if os.path.isdir(refdir) else 0
        rows.append((n, _tok(len(fm.get('name', '')) + len(fm.get('description', ''))), _tok(len(body)), _tok(ref_chars)))
    return rows


def print_tokens():
    rows = token_table()
    print('%-24s %6s %6s %7s' % ('skill', 'desc', 'body', 'refs'))
    for r in rows:
        print('%-24s %6d %6d %7d' % r)
    print('%-24s %6d %6d %7d' % ('TOTAL', sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows)))


# ---------------- build ----------------

def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def _copy_tree(src, dst):
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
                continue
            s = os.path.join(dirpath, fn)
            if os.path.islink(s):
                continue
            t = os.path.join(dst, os.path.relpath(s, src))
            os.makedirs(os.path.dirname(t), exist_ok=True)
            shutil.copyfile(s, t)


def _zip_dir(root, zpath, arc_prefix):
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for fn in sorted(filenames):
                p = os.path.join(dirpath, fn)
                arc = (arc_prefix + '/' + os.path.relpath(p, root).replace('\\', '/')).lstrip('/')
                info = zipfile.ZipInfo(arc, ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(p, 'rb') as fh:
                    z.writestr(info, fh.read())


def build(label=None):
    sync()
    if validate() or scan(quiet=True):
        print('build stopped: fix the FAIL lines first')
        return 1
    version = open(os.path.join(SRC, 'VERSION'), encoding='utf-8').read().strip()
    top = '%s-%s' % (PACK_ID, version)
    stage = os.path.join(DIST, top)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    for fn in sorted(os.listdir(SRC)):
        p = os.path.join(SRC, fn)
        if os.path.isfile(p) and not fn.startswith('.') and os.path.splitext(fn)[1].lower() in TEXT_EXT | {''}:
            shutil.copyfile(p, os.path.join(stage, fn))
    _copy_tree(SKILLS, os.path.join(stage, 'skills'))
    # catalog
    group_of = {n: (gid, title) for gid, title, ns in GROUPS for n in ns}
    tokens = {r[0]: r[1:] for r in token_table()}
    skills = []
    for gid, title, ns in GROUPS:
        for n in ns:
            d = os.path.join(stage, 'skills', n)
            fm, body = parse_skill(d)
            files = []
            for dirpath, _, filenames in os.walk(d):
                for fn in sorted(filenames):
                    p = os.path.join(dirpath, fn)
                    files.append({'path': os.path.relpath(p, d).replace('\\', '/'), 'sha256': _sha(p), 'bytes': os.path.getsize(p)})
            dt, bt, rt = tokens[n]
            skills.append({'name': n, 'group': gid, 'description': fm['description'],
                           'requires': fm.get('compatibility', ''), 'tokens': {'listing': dt, 'body': bt, 'references': rt},
                           'scripts': sorted(f['path'] for f in files if f['path'].startswith('scripts/')),
                           'files': sorted(files, key=lambda x: x['path'])})
    catalog = {'pack': 'STALKER 2 AI Modding Toolkit', 'id': PACK_ID, 'version': version,
               'author': 'STALKER 2 AI Modding Toolkit contributors', 'verified_on': 'STALKER 2 Steam build 26123434 (game 2.1), Zone Kit 2.1.0',
               'groups': [{'id': g, 'title': t, 'skills': ns} for g, t, ns in GROUPS],
               'presets': PRESETS, 'skills': skills}
    with open(os.path.join(stage, 'catalog.json'), 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(catalog, fh, indent=2)
    # per-skill zips for claude.ai (top level = <name>/SKILL.md)
    cz = os.path.join(stage, 'claude-ai')
    os.makedirs(cz)
    for s in skills:
        _zip_dir(os.path.join(stage, 'skills', s['name']), os.path.join(cz, s['name'] + '.zip'), s['name'])
    # checksums
    sums = []
    for dirpath, _, filenames in os.walk(stage):
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            sums.append('%s  %s' % (_sha(p), os.path.relpath(p, stage).replace('\\', '/')))
    with open(os.path.join(stage, 'SHA256SUMS.txt'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(sorted(sums, key=lambda x: x[66:])) + '\n')
    # final zip
    zpath = os.path.join(DIST, top + ('-' + label if label else '') + '.zip')
    if os.path.exists(zpath):
        os.remove(zpath)
    _zip_dir(stage, zpath, top)
    digest = _sha(zpath)
    with open(zpath + '.sha256', 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('%s  %s\n' % (digest, os.path.basename(zpath)))
    # the zip itself must pass the scan rules too (belt and braces)
    bad = 0
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if '\\' in info.filename or info.filename.startswith('/') or '..' in info.filename.split('/'):
                print('FAIL zip entry %r' % info.filename)
                bad += 1
            if os.path.splitext(info.filename)[1].lower() not in TEXT_EXT | {''} and not info.filename.endswith('.zip'):
                print('FAIL zip entry type %r' % info.filename)
                bad += 1
    print('built %s (%d bytes, %d skills)\nsha256 %s' % (zpath, os.path.getsize(zpath), len(skills), digest))
    return 1 if bad else 0


# ---------------- test ----------------

def test():
    version = open(os.path.join(SRC, 'VERSION'), encoding='utf-8').read().strip()
    stage = os.path.join(DIST, '%s-%s' % (PACK_ID, version))
    inst = os.path.join(stage, 'install.py')
    if not os.path.isfile(inst):
        print('FAIL run build first')
        return 1
    fails = 0
    home = tempfile.mkdtemp(prefix='s2pack_test_')
    py = [sys.executable, '-I', inst, '--home', home]

    def run(args, expect=0):
        nonlocal fails
        r = subprocess.run(py + args, capture_output=True, text=True)
        ok = (r.returncode == expect)
        print('%s install.py %s -> %d' % ('ok  ' if ok else 'FAIL', ' '.join(args), r.returncode))
        if not ok:
            fails += 1
            print(r.stdout[-1500:], r.stderr[-1500:])
        return r

    try:
        cat = json.loads(run(['--list', '--json']).stdout)
        names = [s['name'] for s in cat['skills']]
        agents = 'claude-code,agents,kiro,cline'
        run(['--install', 'all', '--agent', agents, '--yes'])
        for root in ('.claude/skills', '.agents/skills', '.kiro/skills', '.cline/skills'):
            for n in names:
                if not os.path.isfile(os.path.join(home, root, n, 'SKILL.md')):
                    print('FAIL missing %s/%s' % (root, n))
                    fails += 1
        if os.path.exists(os.path.join(home, '.claude', 'skills', 'manifest.json')):
            print('FAIL installer wrote manifest.json into a skills folder')
            fails += 1
        run(['--install', 'all', '--agent', 'claude-code', '--yes'])                 # reinstall over our own: ok
        foreign = os.path.join(home, '.agents', 'skills', 'stalker2-foreign')
        os.makedirs(foreign)
        open(os.path.join(foreign, 'SKILL.md'), 'w').write('---\nname: stalker2-foreign\ndescription: x\n---\n')
        mine = os.path.join(home, '.cline', 'skills', names[0])
        shutil.rmtree(mine)
        os.makedirs(mine)
        open(os.path.join(mine, 'SKILL.md'), 'w').write('user copy')
        run(['--install', names[0], '--agent', 'cline', '--yes'], expect=3)               # refuses a skill it did not install
        run(['--install', names[0], '--agent', 'cline', '--yes', '--replace-foreign'])   # backs it up, then installs
        if not os.listdir(os.path.join(home, '.stalker2-skill-pack', 'backups')):
            print('FAIL no backup made')
            fails += 1
        agents_md = os.path.join(home, 'AGENTS.md')
        open(agents_md, 'w').write('# my rules\n')
        run(['--agents-md', agents_md, '--agent', 'agents', '--yes'])
        if 'stalker2-skill-pack:start' not in open(agents_md).read():
            print('FAIL AGENTS.md block missing')
            fails += 1
        run(['--uninstall', 'all', '--agent', agents, '--yes'])
        for root in ('.claude/skills', '.agents/skills', '.kiro/skills', '.cline/skills'):
            left = [x for x in os.listdir(os.path.join(home, root))] if os.path.isdir(os.path.join(home, root)) else []
            expect_left = {'stalker2-foreign'} if root == '.agents/skills' else set()
            if set(left) != expect_left:
                print('FAIL after uninstall %s holds %s' % (root, left))
                fails += 1
        if 'stalker2-skill-pack:start' in open(agents_md).read() or '# my rules' not in open(agents_md).read():
            print('FAIL AGENTS.md block not removed cleanly')
            fails += 1
        run(['--install', 'core', '--agent', 'claude-code', '--scope', 'project', '--project-dir', os.path.join(home, 'proj'),
             '--yes', '--dry-run'])
        if os.path.exists(os.path.join(home, 'proj')):
            print('FAIL dry run wrote files')
            fails += 1
        ex_dir = os.path.join(home, 'excl_proj')
        run(['--install', 'all', '--exclude', 'stalker2-linux,stalker2-saves', '--agent', 'agents',
             '--scope', 'project', '--project-dir', ex_dir, '--yes'])
        ex_skills = os.path.join(ex_dir, '.agents', 'skills')
        if os.path.exists(os.path.join(ex_skills, 'stalker2-linux')) or os.path.exists(os.path.join(ex_skills, 'stalker2-saves')):
            print('FAIL --exclude kept excluded skill(s)')
            fails += 1
        if len(os.listdir(ex_skills)) != len(names) - 2:
            print('FAIL --exclude count mismatch: got %d' % len(os.listdir(ex_skills)))
            fails += 1
        zk_dir = os.path.join(home, 'zk_proj')
        run(['--install', 'zonekit', '--agent', 'claude-code', '--scope', 'project', '--project-dir', zk_dir, '--yes'])
        zk_got = set(os.listdir(os.path.join(zk_dir, '.claude', 'skills')))
        if zk_got != set(PRESETS['zonekit']):
            print('FAIL zonekit preset mismatch: %s' % sorted(zk_got))
            fails += 1
        src_list = subprocess.run([sys.executable, '-I', os.path.join(SRC, 'install.py'), '--list', '--json', '--home', home],
                                  capture_output=True, text=True)
        built_list = subprocess.run([sys.executable, '-I', os.path.join(stage, 'install.py'), '--list', '--json', '--home', home],
                                    capture_output=True, text=True)
        src_cat = json.loads(src_list.stdout)
        stage_cat = json.loads(built_list.stdout)
        src_meta = [(s['name'], s.get('group'), s.get('tokens')) for s in src_cat['skills']]
        stage_meta = [(s['name'], s.get('group'), s.get('tokens')) for s in stage_cat['skills']]
        if src_cat.get('presets') != stage_cat.get('presets') or src_meta != stage_meta:
            print('FAIL source install.py --list --json differs from built release catalog')
            fails += 1
        ign = subprocess.run([sys.executable, '-I', os.path.join(SRC, 'install.py'), '--install', 'core',
                              '--exclude', 'stalker2-audio', '--agent', 'claude-code', '--scope', 'project',
                              '--project-dir', os.path.join(home, 'ign_proj'), '--yes', '--dry-run', '--home', home],
                             capture_output=True, text=True)
        if ign.returncode != 0 or 'not in selection' not in ign.stdout:
            print('FAIL --exclude ignored-skill note check (exit %d): %r' % (ign.returncode, ign.stdout))
            fails += 1
        for zn in os.listdir(os.path.join(stage, 'claude-ai')):
            with zipfile.ZipFile(os.path.join(stage, 'claude-ai', zn)) as z:
                top = {i.filename.split('/')[0] for i in z.infolist()}
                if top != {zn[:-4]} or (zn[:-4] + '/SKILL.md') not in z.namelist():
                    print('FAIL claude-ai zip layout %s' % zn)
                    fails += 1
    finally:
        shutil.rmtree(home, ignore_errors=True)
    print('test: %d FAIL' % fails)
    return 1 if fails else 0


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    only = None
    if '--only' in argv:
        only = set(argv[argv.index('--only') + 1].split(','))
    cmd = argv[0]
    if cmd == 'scan':
        return 1 if scan(only) else 0
    if cmd == 'validate':
        return 1 if validate(only) else 0
    if cmd == 'sync':
        sync()
        return 0
    if cmd == 'tokens':
        print_tokens()
        return 0
    if cmd == 'build':
        return build(argv[argv.index('--label') + 1] if '--label' in argv else None)
    if cmd == 'test':
        return test()
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
