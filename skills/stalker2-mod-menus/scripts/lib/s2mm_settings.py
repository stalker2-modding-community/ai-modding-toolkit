"""S2MM toolkit: read and check a settings file, and write the two Blueprint pastes for a mod's S2MM settings.
Plain Python (no unreal): s2mm_make.py calls it inside the kit, and it can be run on its own to check a file:
    python s2mm_settings.py check <s2mm_settings.json>
MIT licence, part of S2MM (Stalker 2 Mod Menu)."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bpgen import Graph, link, chain, call, event, branch, self_node, obj, BOOL, iface_event, struct, cast
from s2help import (MGR, IFACE, ACTOR, SUBSYS, GS, KML, KStr, S, I, R, VEC, gv, sv, pure, eqs, parse, item, get_manager, spawn_keep,
                    add_mod, add_setting)

TYPES = {
    # type: (variable kind or None, what the player sees)
    'header': (None, 'a section heading'),
    'toggle': ('bool', 'a checkbox'),
    'slider': ('real', 'a slider with decimals (min, max, step)'),
    'intslider': ('int', 'a slider with whole numbers (min, max, step)'),
    'number': ('real', 'a number box with decimals, no range'),
    'intnumber': ('int', 'a number box with whole numbers, no range'),
    'choice': ('int', 'a  < option >  selector (options); the variable holds the index of the picked option, 0 = first'),
    'info': (None, 'a line of text (text)'),
    'color': ('vector', 'a colour: three number boxes R, G, B, each 0 to 255, and a colour square (default [r, g, b], e.g. [255, 128, 0])'),
    'button': (None, 'a button (text = what it says); S2MM_OnValue tells you when it is pressed'),
    'key': ('string', 'a key picker (A / Enter, then the key); the variable holds the name of the key, e.g. "F6", or None when the player cleared it with Delete'),
}
KEY_NAMES = ('F1 to F12, ~, Insert, Home, End, Page Up, Page Down, Num 0 to Num 9, Multiply, Add, Subtract, Divide, Decimal, Pause, '
             'Scroll Lock')
RESERVED = {'Manager', 'self', 'None', 'True', 'False'}
BIG = 1000000.0


class SettingsError(Exception):
    pass


def load(path):
    """read and check a settings file; returns the dict, raises SettingsError with every problem found"""
    try:
        cfg = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        raise SettingsError('cannot read %s: %s' % (path, e))
    errs = []
    for k in ('mod', 'name'):
        if not isinstance(cfg.get(k), str) or not cfg.get(k):
            errs.append('"%s" is missing (text)' % k)
    if cfg.get('mod') and not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', cfg['mod']):
        errs.append('"mod" must be your kit mod folder name (letters, digits, _): %r' % cfg['mod'])
    cfg.setdefault('id', (cfg.get('mod') or '').lower())
    cfg.setdefault('author', '')
    cfg.setdefault('group', 'S2MM')
    if not re.match(r'^[A-Za-z0-9_.-]+$', cfg['id']):
        errs.append('"id" may only use letters, digits, _ . - : %r' % cfg['id'])
    sets = cfg.get('settings')
    if not isinstance(sets, list) or not sets:
        errs.append('"settings" must be a list with at least one setting')
        sets = []
    seen = set()
    for n, s in enumerate(sets, 1):
        where = 'setting %d (%s)' % (n, s.get('id', '?') if isinstance(s, dict) else '?')
        if not isinstance(s, dict):
            errs.append(where + ': must be { ... }'); continue
        sid, typ = s.get('id'), s.get('type')
        if not isinstance(sid, str) or not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', sid):
            errs.append(where + ': "id" must start with a letter and use only letters, digits, _ (it becomes a variable name)')
        elif sid in seen:
            errs.append(where + ': the id is used twice')
        elif sid in RESERVED:
            errs.append(where + ': "%s" is reserved, pick another id' % sid)
        seen.add(sid)
        if typ not in TYPES:
            errs.append(where + ': "type" must be one of %s' % ', '.join(TYPES)); continue
        s.setdefault('label', sid)
        s.setdefault('desc', '')
        if typ == 'toggle':
            s.setdefault('default', False)
            if not isinstance(s['default'], bool):
                errs.append(where + ': "default" must be true or false')
        if typ in ('slider', 'intslider'):
            for k in ('min', 'max'):
                if not isinstance(s.get(k), (int, float)):
                    errs.append(where + ': "%s" is needed (a number)' % k)
            s.setdefault('step', 1 if typ == 'intslider' else 0.1)
            s.setdefault('default', s.get('min', 0))
            if isinstance(s.get('min'), (int, float)) and isinstance(s.get('max'), (int, float)) and s['min'] >= s['max']:
                errs.append(where + ': "min" must be smaller than "max"')
        if typ in ('number', 'intnumber'):
            s.setdefault('default', 0)
            s.setdefault('step', 1 if typ == 'intnumber' else 0.1)
        if typ in ('intslider', 'intnumber'):
            for k in ('default', 'min', 'max', 'step'):
                if k in s and isinstance(s[k], float) and not s[k].is_integer():
                    errs.append(where + ': "%s" must be a whole number' % k)
        if typ == 'choice':
            o = s.get('options')
            if not isinstance(o, list) or len(o) < 2 or not all(isinstance(x, str) and x and '|' not in x for x in o):
                errs.append(where + ': "options" must be a list of at least two names (no | in them)')
            s.setdefault('default', 0)
            if isinstance(o, list) and not (isinstance(s['default'], int) and 0 <= s['default'] < len(o)):
                errs.append(where + ': "default" is the index of the first-shown option: 0 to %d' % (len(o) - 1))
        if typ == 'info':
            s.setdefault('text', '')
        if typ == 'button':
            s.setdefault('text', 'PRESS')
            if not isinstance(s['text'], str) or not s['text'] or '|' in s['text']:
                errs.append(where + ': "text" is what the button says (text, no |)')
        if typ == 'key':
            d = s.get('default')
            if not isinstance(d, str) or not d.strip():
                errs.append(where + ': "default" is the name of the key, e.g. "F6" (S2MM can catch: %s)' % KEY_NAMES)
        if typ == 'color':
            d = s.setdefault('default', [255, 255, 255])
            if not (isinstance(d, list) and len(d) == 3 and all(isinstance(x, (int, float)) for x in d)):
                errs.append(where + ': "default" must be three numbers, 0 to 255, e.g. [255, 128, 0]')
    if errs:
        raise SettingsError('\n'.join(errs))
    return cfg


def names(cfg):
    mod = cfg['mod']
    folder = '/%s/S2MM' % mod
    prov = '%s/BP_%s_S2MM' % (folder, mod)
    sub = '%s/BP_%s_S2MMSubsystem' % (folder, mod)
    return {'folder': folder, 'provider': prov, 'provider_class': '%s.BP_%s_S2MM_C' % (prov, mod),
            'subsystem': sub, 'subsystem_class': '%s.BP_%s_S2MMSubsystem_C' % (sub, mod)}


def value_settings(cfg):
    """the settings that get a variable"""
    return [s for s in cfg['settings'] if TYPES[s['type']][0]]


def onvalue_settings(cfg):
    """the settings S2MM_OnValue handles: every value setting, and buttons (to react to a press)"""
    return [s for s in cfg['settings'] if TYPES[s['type']][0] or s['type'] == 'button']


def fnum(x):
    return '%f' % float(x)


def provider_graph(cfg):
    """the provider's Event Graph: S2MM_Register adds the mod and every setting; S2MM_OnValue stores a changed value in its variable"""
    g = Graph('S2P')
    mid = cfg['id']
    g.box(-60, -140, 1400 + 350 * len(cfg['settings']), 700,
          'S2MM (made by s2mm_make.py): when S2MM asks, add this mod and its settings. Change them in s2mm_settings.json and run the script again')
    rg = iface_event(g, 0, 0, IFACE, 'S2MM_Register')
    ga, c, mgr = get_manager(g, 300, 0)
    link(rg.exec_out, ga.exec_in)
    sm = sv(g, 950, 0, 'Manager', obj(MGR), src=mgr)
    link(c.exec_out, sm.exec_in)
    me = lambda x, y: gv(g, x, y, 'Manager', obj(MGR))
    slf = lambda x, y: self_node(g, x, y).val
    calls = [add_mod(g, 1250, 0, me(1100, 200), slf(1100, 280), mid, cfg['name'], cfg['author'], cfg['group'])]
    for k, s in enumerate(cfg['settings']):
        x = 1600 + 350 * k
        t = s['type']
        if t in ('button', 'key'):
            # no helper for these on the manager: the long form, S2MM_AddSetting (Type "button" / "key")
            n = add_setting(g, x, 0, me(x - 150, 200), slf(x - 150, 280), mid, s['id'], t, s['label'], s['desc'],
                            s['default'] if t == 'key' else '0', opts=s['text'] if t == 'button' else '')
            calls.append(n)
            continue
        fn = {'header': 'S2MM_AddHeader', 'toggle': 'S2MM_AddToggle', 'slider': 'S2MM_AddSlider', 'number': 'S2MM_AddSlider',
              'intslider': 'S2MM_AddIntSlider', 'intnumber': 'S2MM_AddIntSlider', 'choice': 'S2MM_AddChoice', 'info': 'S2MM_AddInfo',
              'color': 'S2MM_AddColor'}[t]
        n = call(g, x, 0, MGR, fn, target=MGR)
        link(me(x - 150, 200), n.target)
        link(slf(x - 150, 280), n.pin('Provider', **obj(ACTOR)))
        n.pin('ModID', default=mid, **S); n.pin('SettingID', default=s['id'], **S); n.pin('Label', default=s['label'], **S)
        if t != 'header':
            n.pin('Desc', default=s['desc'], **S)
        if t == 'toggle':
            n.pin('Default', cat='bool', default='true' if s['default'] else 'false')
        elif t in ('slider', 'number'):
            lo, hi = (s['min'], s['max']) if t == 'slider' else (-BIG, BIG)
            n.pin('Default', default=fnum(s['default']), **R); n.pin('Min', default=fnum(lo), **R)
            n.pin('Max', default=fnum(hi), **R); n.pin('Step', default=fnum(s['step']), **R)
        elif t in ('intslider', 'intnumber'):
            lo, hi = (s['min'], s['max']) if t == 'intslider' else (-int(BIG), int(BIG))
            n.pin('Default', default=str(int(s['default'])), **I); n.pin('Min', default=str(int(lo)), **I)
            n.pin('Max', default=str(int(hi)), **I); n.pin('Step', default=str(int(s['step'])), **I)
        elif t == 'choice':
            n.pin('Options', default='|'.join(s['options']), **S); n.pin('DefaultIndex', default=str(s['default']), **I)
        elif t == 'info':
            n.pin('Text', default=s['text'], **S)
        elif t == 'color':
            n.pin('Default', default=','.join(fnum(v) for v in s['default']), **VEC)
        calls.append(n)
    chain(sm, *calls)

    Y = 1000
    vs = onvalue_settings(cfg)
    g.box(-60, Y - 140, 1600 + 350 * max(1, len(vs)), 300 + 300 * max(1, len(vs)),
          'S2MM_OnValue (a value changed): if it is ours, put it in the variable with the same name as the setting. Read those variables anywhere in your mod')
    ov = iface_event(g, 0, Y, IFACE, 'S2MM_OnValue')
    b0 = branch(g, 300, Y)
    link(ov.exec_out, b0.exec_in)
    link(eqs(g, 200, Y + 200, gv(g, 50, Y + 200, 'LastMod', S, parent=MGR, target_src=me(-100, Y + 200)), mid), b0.cond)
    lid = lambda x, y: gv(g, x, y, 'LastID', S, parent=MGR, target_src=me(x - 150, y))
    last = lambda x, y, nm, ty: gv(g, x, y, nm, ty, parent=MGR, target_src=me(x - 150, y))
    prev = b0.t
    for k, s in enumerate(vs):
        y = Y + 300 * k
        bx = branch(g, 600 + 300 * k, y)
        link(prev, bx.exec_in)
        link(eqs(g, 500 + 300 * k, y + 200, lid(350 + 300 * k, y + 200), s['id']), bx.cond)
        kind = TYPES[s['type']][0]
        x = 900 + 300 * k
        if kind == 'bool':
            st = sv(g, x, y - 120, s['id'], BOOL, src=last(x - 150, y - 20, 'LastBool', BOOL))
        elif kind == 'int':
            st = sv(g, x, y - 120, s['id'], I, src=last(x - 150, y - 20, 'LastInt', I))
        elif kind == 'real':
            st = sv(g, x, y - 120, s['id'], R, src=last(x - 150, y - 20, 'LastFloat', R))
        elif kind == 'string':   # a key setting: the key's name
            st = sv(g, x, y - 120, s['id'], S, src=last(x - 150, y - 20, 'LastValue', S))
        elif kind is None:   # a button: nothing to store. A press sends LastValue "press"; a loading save re-sends the stored "0"
            bp_ = branch(g, x, y - 120)
            link(bx.t, bp_.exec_in)
            link(eqs(g, x - 100, y + 80, last(x - 250, y + 80, 'LastValue', S), 'press'), bp_.cond)
            g.box(x - 60, y - 300, 1000, 260, 'Button "%s" was pressed: add your nodes to the True pin of this Branch (LastValue is "press")' % s['id'])
            prev = bx.f
            continue
        else:   # vector from "x,y,z"
            arr = parse(g, x - 450, y + 40, last(x - 600, y + 40, 'LastValue', S), ',')
            comp = lambda j: pure(g, x - 150, y - 60 + 80 * j, KStr, 'Conv_StringToDouble',
                                  [('InString', item(g, x - 300, y - 60 + 80 * j, arr, pure(g, x - 450, y - 60 + 80 * j, KML, 'Max',
                                                                                               [('A', None, I, str(j)), ('B', None, I, str(j))], I), S), S, None)], R)
            mk = pure(g, x - 50, y + 100, KML, 'MakeVector', [('X', comp(0), R, None), ('Y', comp(1), R, None), ('Z', comp(2), R, None)], VEC)
            st = sv(g, x, y - 120, s['id'], VEC, src=mk)
        link(bx.t, st.exec_in)
        prev = bx.f
    return g


def subsystem_graph(cfg):
    """the starter: a ModWorldSubsystem that keeps the provider actor alive"""
    nm = names(cfg)
    g = Graph('S2SS')
    g.box(-60, -120, 1100, 260, 'S2MM (made by s2mm_make.py): start ticking when the world subsystem starts')
    ini = event(g, 0, 0, SUBSYS, 'OnInitialized')
    st = call(g, 400, 0, SUBSYS, 'SetTickEnabled', target=SUBSYS)
    st.pin('bIsEnabled', cat='bool', default='true')
    link(ini.exec_out, st.exec_in)
    link(self_node(g, 200, 120).val, st.target)
    g.box(-60, 260, 1900, 500, 'S2MM (made by s2mm_make.py): keep this mod\'s S2MM settings actor alive')
    tk = event(g, 0, 400, SUBSYS, 'OnTick', outs=[('DeltaTime', dict(cat='real', sub='float'))])
    spawn_keep(g, 400, 400, 'Provider', nm['provider_class'], tk.exec_out)
    return g


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'check':
        try:
            c = load(sys.argv[2])
            print('OK: %s, %d settings' % (c['name'], len(c['settings'])))
        except SettingsError as e:
            print('PROBLEMS:\n' + str(e))
            sys.exit(1)
    else:
        print(__doc__)
