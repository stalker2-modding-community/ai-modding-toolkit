"""S2MM toolkit: convert a mod made for MCM (Mod Configuration Menu) to S2MM.

Run it INSIDE the Zone Kit with your mod open: File > Execute Python Script > pick this file.
(It also runs headless. Set the mod with the S2MM_CONVERT_MOD environment variable, or write the mod name in
s2mm_convert.txt next to this script.)

What it does (it only READS your mod; nothing is changed):
  1. reads every Blueprint of your mod and finds each MCM "RegisterModSetting" call: mod id, setting id, type, default, hover text,
     category, dropdown options
  2. writes out/<YourMod>/s2mm_settings.json in the S2MM settings format (one header per MCM category)
  3. writes out/<YourMod>/conversion_report.md: what was converted, what could not be (and why), and every "GetModSetting" read
     to swap for the S2MM variable of the same name
Then: check the settings file, copy it next to s2mm_make.py as s2mm_settings.json, and run s2mm_make.py.
MCM is not needed by your mod afterwards. Values players set in MCM live in their game saves and do not carry over.
MIT licence, part of S2MM (Stalker 2 Mod Menu). It reads only YOUR mod's files and uses MCM's public function names."""
import os, re, sys, json, traceback
import unreal

try:
    ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:      # the kit normally sets __file__; if not, say where the toolkit is with the S2MM_TOOLKIT environment variable
    ROOT = os.environ.get('S2MM_TOOLKIT', os.getcwd())
EAL = unreal.EditorAssetLibrary
lines = []
OUT = [None]
# MCM's setting types (E_MCM_SettingType, in order)
MCM_TYPES = ['Bool', 'Int', 'Float', 'String', 'Transform', 'Vector', 'Rotator', 'ComboBox', 'Keybind', 'Button']


def say(*a):
    s = ' '.join(str(x) for x in a)
    lines.append(s)
    unreal.log('[S2MM convert] ' + s)


def which_mod():
    m = os.environ.get('S2MM_CONVERT_MOD')
    if not m:
        f = os.path.join(ROOT, 's2mm_convert.txt')
        if os.path.isfile(f):
            m = open(f, encoding='utf-8').read().strip()
    if not m:
        raise RuntimeError('write your kit mod folder name in %s (one line), then run again' % os.path.join(ROOT, 's2mm_convert.txt'))
    return m


def export_t3d(asset, tmp):
    t = unreal.AssetExportTask()
    t.object, t.filename, t.automated, t.prompt, t.replace_identical, t.exporter = asset, tmp, True, False, True, None
    unreal.Exporter.run_asset_export_task(t)
    txt = open(tmp, encoding='utf-8', errors='replace').read() if os.path.isfile(tmp) else ''
    if os.path.isfile(tmp):
        os.remove(tmp)
    return txt


def nodes_of(txt):
    """{node name: {'class', 'graph', 'pins': {pin name: {'default', 'links': [node names]}}, 'fn'}} from a Blueprint's T3D export,
    graph nodes only (the compiled ubergraph copies are skipped)"""
    out = {}
    lines_ = txt.splitlines()
    for i, l in enumerate(lines_):
        m = re.match(r'^(\s*)Begin Object Name="(K2Node_\w+)" ExportPath="([^"]*)"', l)
        if not m or 'ExecuteUbergraph' in m.group(3):
            continue
        ind, name, path = m.groups()
        j = i + 1
        while j < len(lines_) and not (lines_[j].strip() == 'End Object' and len(lines_[j]) - len(lines_[j].lstrip()) == len(ind)):
            j += 1
        blk = '\n'.join(lines_[i:j])
        if name in out:
            continue
        cls = re.search(r"/Script/BlueprintGraph\.(K2Node_\w+)'", path)
        graph = re.search(r":([^.:]+)\.%s'" % re.escape(name), path)
        fn = re.search(r'MemberName="([^"]+)"', blk)
        pins = {}
        for p in re.findall(r'CustomProperties Pin \(([^\n]*)\)', blk):
            pn = re.search(r'PinName="([^"]*)"', p)
            if not pn:
                continue
            d = re.search(r'DefaultValue="((?:[^"\\]|\\.)*)"', p)
            lk = re.search(r'LinkedTo=\(([^)]*)\)', p)
            pins[pn.group(1)] = {'default': d.group(1) if d else None,
                                 'links': [x.split()[0] for x in lk.group(1).split(',') if x.strip()] if lk else [],
                                 'out': 'EGPD_Output' in p}
        out[name] = {'class': cls.group(1) if cls else name.rsplit('_', 1)[0], 'graph': graph.group(1) if graph else '?',
                     'pins': pins, 'fn': fn.group(1) if fn else ''}
    return out


def pin_value(nodes, node, pin):
    """(value, how): a literal default, the elements of a Make Array, or None when the value is computed at run time"""
    p = nodes[node]['pins'].get(pin)
    if p is None:
        return None, 'missing'
    if not p['links']:
        return p['default'], 'literal'
    src = nodes.get(p['links'][0])
    if src and src['class'] == 'K2Node_MakeArray':
        el = sorted(((int(re.sub(r'\D', '', k) or 0), v['default']) for k, v in src['pins'].items() if re.match(r'^\[\d+\]$', k)))
        if all(v is not None and not src['pins']['[%d]' % i]['links'] for i, v in el):
            return [v for _, v in el], 'make array'
    return None, 'computed (linked to %s)' % (src['class'] if src else '?')


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def main():
    mod = which_mod()
    out = os.path.join(ROOT, 'out', mod)
    os.makedirs(out, exist_ok=True)
    OUT[0] = out
    tmp = os.path.join(out, '_bp.t3d')
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    reg.scan_paths_synchronous(['/%s/' % mod], True)
    assets = [a for a in reg.get_assets_by_path('/%s' % mod, True) if str(a.asset_class_path.asset_name) in ('Blueprint', 'WidgetBlueprint')]
    say('mod', mod, '|', len(assets), 'Blueprints')
    regs, reads, notes = [], [], []
    for a in assets:
        bp = unreal.load_asset(str(a.package_name))
        if not bp:
            continue
        nodes = nodes_of(export_t3d(bp, tmp))
        for nn, n in nodes.items():
            if n['class'] not in ('K2Node_Message', 'K2Node_CallFunction'):
                continue
            if n['fn'] == 'RegisterModSetting':
                r = {'bp': bp.get_name(), 'graph': n['graph'], 'node': nn}
                for pin in ('ModID', 'SettingID', 'SettingHoverText', 'AuthorName', 'Category', 'Type', 'BoolValue', 'IntValue', 'FloatValue',
                            'FloatControllerStepValue', 'StringValue', 'VectorValue', 'RotatorValue', 'ComboBoxOptions', 'ComboBoxSelectedOption'):
                    r[pin], r[pin + '_how'] = pin_value(nodes, nn, pin)
                regs.append(r)
            elif n['fn'] == 'GetModSetting':
                sid, how = pin_value(nodes, nn, 'SettingID')
                used = [p for p, v in n['pins'].items() if v['out'] and v['links'] and p not in ('then',)]
                reads.append({'bp': bp.get_name(), 'graph': n['graph'], 'node': nn, 'setting': sid if how == 'literal' else '(%s)' % how, 'outputs': used})
    say('RegisterModSetting calls:', len(regs), '| GetModSetting reads:', len(reads))
    if not regs:
        raise RuntimeError('no MCM RegisterModSetting call found in /%s/ (is this the right mod?)' % mod)
    # ---- settings file
    mids = sorted({r['ModID'] for r in regs if r['ModID']})
    if len(mids) > 1:
        notes.append('This mod registers several MCM mod ids (%s). All settings were put under one S2MM mod; split the file if you want several.' % ', '.join(mids))
    cfg = {'mod': mod, 'id': (mids[0] if mids else mod.lower()).replace(' ', '_'), 'name': mids[0] if mids else mod,
           'author': next((r['AuthorName'] for r in regs if r['AuthorName']), ''), 'group': 'S2MM', 'settings': []}
    cat, used_ids, conv, skipped = None, set(), [], []
    for r in regs:
        where = '%s > %s (%s)' % (r['bp'], r['graph'], r['node'])
        sid = r['SettingID'] if r['SettingID_how'] == 'literal' else None
        if not sid:
            skipped.append((where, 'the setting id is %s, not typed in: add it by hand' % r['SettingID_how'])); continue
        var = re.sub(r'[^A-Za-z0-9_]', '_', sid)
        if not re.match(r'^[A-Za-z]', var):
            var = 'S_' + var
        if var in used_ids:
            skipped.append((where, 'setting id "%s" used twice' % sid)); continue
        t = r['Type'] if r['Type_how'] == 'literal' else None
        ti = int(re.sub(r'\D', '', t)) if t and re.search(r'\d', t) else (MCM_TYPES.index(t) if t in MCM_TYPES else None)
        if ti is None:
            skipped.append((where, '%s: the type is %s, not typed in' % (sid, r['Type_how']))); continue
        mt = MCM_TYPES[ti]
        if r['Category'] and r['Category'] != cat:
            cat = r['Category']
            hid = 'h_' + re.sub(r'[^A-Za-z0-9_]', '_', cat)
            if hid not in used_ids:
                cfg['settings'].append({'id': hid, 'type': 'header', 'label': cat}); used_ids.add(hid)
        s = {'id': var, 'label': sid, 'desc': r['SettingHoverText'] or ''}
        dyn = [p for p in ('BoolValue', 'IntValue', 'FloatValue', 'VectorValue', 'ComboBoxOptions', 'ComboBoxSelectedOption') if r[p + '_how'].startswith('computed')]
        if mt == 'Bool':
            s.update(type='toggle', default=str(r['BoolValue']).lower() == 'true')
        elif mt == 'Int':
            s.update(type='intnumber', default=int(num(r['IntValue'])))
        elif mt == 'Float':
            st = num(r['FloatControllerStepValue'], 0.1) or 0.1
            s.update(type='number', default=num(r['FloatValue']), step=st)
        elif mt == 'ComboBox':
            opts = r['ComboBoxOptions'] if isinstance(r['ComboBoxOptions'], list) else None
            if not opts or len(opts) < 2:
                skipped.append((where, '%s: dropdown options are %s: add "options" by hand' % (sid, r['ComboBoxOptions_how']))); continue
            s.update(type='choice', options=[o.replace('|', '/') for o in opts], default=int(num(r['ComboBoxSelectedOption'])))
        elif mt in ('Vector', 'Rotator'):
            v = r['VectorValue' if mt == 'Vector' else 'RotatorValue'] or '0,0,0'
            parts = [num(x) for x in re.findall(r'-?[\d.]+(?:e-?\d+)?', v)][:3] + [0, 0, 0]
            s.update(type='color', default=parts[:3])
            if mt == 'Rotator':
                notes.append('%s was an MCM Rotator: it is three numbers (pitch, yaw, roll) in S2MM; make a Rotator from the vector.' % sid)
        elif mt == 'Button':
            s.update(type='button', text='PRESS')
            notes.append('%s was an MCM button: in S2MM a press reaches S2MM_OnValue with LastValue "press" (the made graph has a Branch for it: '
                         'move what your mod did on the MCM press there). Change "text" for what the button says.' % sid)
        elif mt == 'Keybind':
            s.update(type='key', default='')
            notes.append('%s was an MCM key bind: in S2MM it is a key picker and its variable holds the key\'s NAME (text, e.g. "F6"). Write the '
                         'default key name in "default" (the settings check stops until you do). S2MM can catch F-keys, ~, Insert, Home, End, '
                         'Page Up / Down and the number pad; to test the key in your mod, compare the name with Key Get Display Name '
                         '(Long Display Name on) of the key you poll.' % sid)
        else:
            skipped.append((where, '%s: MCM type %s has no S2MM equivalent yet (text fields and transforms are not supported)' % (sid, mt)))
            continue
        if dyn:
            notes.append('%s: %s computed at run time; the converter used the typed default (check "default").' % (sid, ', '.join(dyn)))
        cfg['settings'].append(s); used_ids.add(var)
        conv.append((sid, mt, s['type'], var))
    # drop section headings left with no settings under them (all of theirs were skipped)
    kept = []
    for i, s in enumerate(cfg['settings']):
        nxt = cfg['settings'][i + 1] if i + 1 < len(cfg['settings']) else None
        if s['type'] == 'header' and (nxt is None or nxt['type'] == 'header'):
            continue
        kept.append(s)
    cfg['settings'] = kept
    p = os.path.join(out, 's2mm_settings.json')
    open(p, 'w', encoding='utf-8').write(json.dumps(cfg, indent=2) + '\n')
    say('wrote', p, '|', len(conv), 'settings converted,', len(skipped), 'not converted')
    # ---- report
    rep = ['# MCM -> S2MM conversion report: %s' % mod, '',
           'Settings file: `s2mm_settings.json` (this folder). Check it, copy it next to `s2mm_make.py` as `s2mm_settings.json`, run `s2mm_make.py`.', '',
           '## Converted (%d)' % len(conv), '', '| MCM setting | MCM type | S2MM type | variable on BP_%s_S2MM |' % mod, '|---|---|---|---|']
    rep += ['| %s | %s | %s | `%s` |' % c for c in conv]
    rep += ['', '## Not converted (%d)' % len(skipped), '']
    rep += ['- %s: %s' % s for s in skipped] or ['- none']
    rep += ['', '## Notes', ''] + (['- ' + n for n in notes] or ['- none'])
    rep += ['', '## Reads to swap (%d GetModSetting)' % len(reads), '',
            'Replace each with the S2MM variable of the same name (Get Actor Of Class BP_%s_S2MM > Cast > the variable), or call '
            'S2MM_Get on the S2MM manager and read ResultBool / ResultInt / ResultFloat.' % mod, '']
    rep += ['- %s > %s: `%s` (outputs used: %s)' % (r['bp'], r['graph'], r['setting'], ', '.join(r['outputs']) or 'none') for r in reads] or ['- none']
    rep += ['', '## Then', '', '- Remove the MCM interface (BPI_MCM_SettingsProvider) and the MCM calls from your Blueprints, and MCM from your .uplugin dependencies.',
            '- Values players set in MCM live in their game saves and do not carry over: S2MM starts from your defaults.']
    open(os.path.join(out, 'conversion_report.md'), 'w', encoding='utf-8').write('\n'.join(rep) + '\n')
    say('wrote', os.path.join(out, 'conversion_report.md'))
    say('ALL DONE')


try:
    main()
except Exception:
    say('FAILED', traceback.format_exc())
rp = os.path.join(OUT[0] or ROOT, 's2mm_convert_report.txt')
open(rp, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
unreal.log('[S2MM convert] report: ' + rp)
