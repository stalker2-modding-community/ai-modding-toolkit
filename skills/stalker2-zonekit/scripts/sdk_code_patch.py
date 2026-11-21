r"""Rewrite a Custom node's CODE, or a scalar parameter's default, inside a saved Zone Kit material, without the editor.

A Custom node's code is one ANSI string in its export, stored once: new code that is NOT LONGER than the saved string is
padded with spaces to the same byte length, so no offset in the package moves. The node's INPUTS must stay the same (new
inputs need the editor), so when you create a node in the editor, give it every input it may need and end its code with a
comment block as spare room for longer rewrites. Every write renews the material's StateId (otherwise the cook takes the
OLD shaders from the DDC) and is read back. Then cook (sdk_cook_mod.py <mod>). Close the material in the editor first.

    python sdk_code_patch.py <material.uasset> --list                         Custom nodes (by title) and their code sizes
    python sdk_code_patch.py <material.uasset> --show <title>                 print a node's saved code
    python sdk_code_patch.py <material.uasset> --code <title> <new.hlsl>      write new code (line breaks become CRLF, as the editor)
    python sdk_code_patch.py <material.uasset> --set <Param>=0.8 [--set <Other>=250]    scalar defaults (any stored ScalarParameter)
    add --no-backup to skip the <file>.bak copy (written before every change, the file as it was before this write)

<material.uasset> is the checked-out copy in <kit>/Stalker2/Mods/<mod>/Content/... Needs uasset-dump (see s2paths.py).
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2paths
from sdk_renew_state_id import backup, check_uncooked, dump, renew


def props(e):
    data = e.get('Data')
    return {x['Name']: x for x in data if isinstance(x, dict) and 'Name' in x} if isinstance(data, list) else {}


def customs(d):
    """{title: [Custom node exports with that title]}"""
    out = {}
    for e in d.get('Exports') or []:
        pr = props(e)
        if 'MaterialExpressionCustom' in e.get('ObjectName', '') and isinstance(pr.get('Code', {}).get('Value'), str):
            out.setdefault(pr.get('Description', {}).get('Value'), []).append(e)
    return out


def one_custom(nodes, title):
    hits = nodes.get(title)
    if not hits:
        raise SystemExit('no Custom node titled %r (titles: %s)' % (title, ', '.join(sorted(str(n) for n in nodes if n))))
    if len(hits) > 1:
        raise SystemExit('%d Custom nodes are titled %r: give them distinct titles in the editor first' % (len(hits), title))
    return hits[0]


def code_at(raw, e):
    code = props(e)['Code']['Value']
    blob = bytes(raw[e['SerialOffset']:e['SerialOffset'] + e['SerialSize']])
    b = code.encode('latin-1', errors='replace')
    at = blob.find(b)
    if blob.count(b) != 1 or at < 4 or at + len(b) >= len(blob) or \
            struct.unpack_from('<i', blob, at - 4)[0] != len(b) + 1 or blob[at + len(b)] != 0:
        raise SystemExit('the code of %s is not one plain ANSI string in its export, refusing'
                         % props(e).get('Description', {}).get('Value'))
    return code, e['SerialOffset'] + at


def scalars(d):
    """{parameter name: [every ScalarParameter export of that name]}. Parameters of one name share one value in a material,
    so a default is set on ALL of them (setting only the first can hit a dead copy)."""
    out = {}
    for x in d.get('Exports') or []:
        pr = props(x)
        name = pr.get('ParameterName', {}).get('Value')
        if isinstance(name, str) and isinstance(pr.get('DefaultValue', {}).get('Value'), (int, float)) \
                and 'ScalarParameter' in x.get('ObjectName', ''):
            out.setdefault(name, []).append(x['ObjectName'])
    return out


def locate(d, raw, knobs):
    """knobs {key: (export ObjectName, property)} -> {key: (absolute offset of the float32, current value) or None}.
    None = the property is at its engine default, so it is not in the file (set any other value once in the editor)."""
    out = {}
    exports = {e.get('ObjectName'): e for e in d.get('Exports') or []}
    names = d.get('NameMap') or []
    for knob, (node, prop) in knobs.items():
        e = exports.get(node)
        if e is None:
            raise SystemExit('node %s missing from the asset' % node)
        val = next((float(p['Value']) for p in e.get('Data') or [] if isinstance(p, dict) and p.get('Name') == prop), None)
        if val is None:
            out[knob] = None
            continue
        off, size = e['SerialOffset'], e['SerialSize']
        pat = struct.pack('<f', val)
        blob = raw[off:off + size]
        hits = [i for i in range(len(blob) - 3) if blob[i:i + 4] == pat]
        if len(hits) > 1 and prop in names:
            # The same float can occur elsewhere in the export. A tagged property starts with its FName (name-map index,
            # number 0); keep the hit that follows this property's own tag. The value sits after the whole tag header
            # (UE 5.5: name 8 + type 8 + type params 4 + size 4 + flags 1 = 25 bytes): a hit closer than that is INSIDE
            # the header (a value of exactly 0 matches the zero bytes of its own tag).
            tag = struct.pack('<ii', names.index(prop), 0)
            tags = [i for i in range(len(blob) - 7) if blob[i:i + 8] == tag]
            hits = [h for h in hits if any(25 <= h - t <= 64 for t in tags)]
            if len(hits) > 1:      # the same value on two properties of one node (Lerp A == B): the one nearest its own tag
                near = {h: min(h - t for t in tags if 25 <= h - t) for h in hits}
                hits = [min(hits, key=near.get)]
        if len(hits) != 1:
            raise SystemExit('%s.%s = %s found %d times in its export, refusing' % (node, prop, val, len(hits)))
        out[knob] = (off + hits[0], val)
    return out


def flag_value(a, flag, n=1):
    i = a.index(flag)
    vals = a[i + 1:i + 1 + n]
    if len(vals) < n or any(v.startswith('--') for v in vals):
        raise SystemExit('%s needs %d value(s)' % (flag, n))
    return vals


def f32(v):
    return struct.unpack('<f', struct.pack('<f', v))[0]


def main():
    a = sys.argv[1:]
    if not a or '-h' in a or '--help' in a:
        print(__doc__)
        return 0 if a else 2
    asset = a[0]
    check_uncooked(asset)
    no_backup = '--no-backup' in a
    sets = {}
    for i, x in enumerate(a):
        if x == '--set':
            if i + 1 >= len(a) or a[i + 1].count('=') != 1:
                raise SystemExit('--set needs Name=value, e.g. --set Density=0.8')
            k, v = a[i + 1].split('=')
            try:
                sets[k.strip()] = float(v)
            except ValueError:
                raise SystemExit('--set %s: %r is not a number' % (k, v))
    new_code = None
    if '--code' in a:
        title, path = flag_value(a, '--code', 2)
        if not os.path.isfile(path):
            raise SystemExit('no such code file: %s' % path)
        with open(path, encoding='utf-8') as fh:
            new_code = fh.read().rstrip().replace('\r\n', '\n').replace('\n', '\r\n')
        try:
            new_code.encode('latin-1')
        except UnicodeEncodeError:
            raise SystemExit('the new code has characters outside ANSI (Latin-1); use plain ASCII')

    d = dump(asset, 'sdk_code_patch')
    with open(asset, 'rb') as fh:
        raw = bytearray(fh.read())
    nodes = customs(d)
    if '--list' in a:
        for k in sorted(n for n in nodes if n):
            for e in nodes[k]:
                print('  Custom   %-24s %5d bytes%s' % (k, len(props(e)['Code']['Value']), '   (title used twice)' if len(nodes[k]) > 1 else ''))
        untitled = len(nodes.get(None, []))
        if untitled:
            print('  (%d Custom node(s) without a title: give them one in the editor to patch them)' % untitled)
        sc = scalars(d)
        for k in sorted(sc):
            exps = [x for x in d.get('Exports') or [] if x.get('ObjectName') in sc[k]]
            vals = [props(x).get('DefaultValue', {}).get('Value') for x in exps]
            print('  Scalar   %-24s = %s (x%d)' % (k, vals[0] if vals else 'None', len(sc[k])))
        return 0
    if '--show' in a:
        title = flag_value(a, '--show')[0]
        hits = nodes.get(title) or [one_custom(nodes, title)]
        for n, e in enumerate(hits, 1):
            if len(hits) > 1:
                print('--- %s, copy %d of %d (%s)' % (title, n, len(hits), e.get('ObjectName')))
            print(props(e)['Code']['Value'])
        return 0
    changed = []
    if new_code is not None:
        code, at = code_at(raw, one_custom(nodes, title))
        room = len(code)       # the whole saved string is the room: trailing spaces are an earlier rewrite's padding
        if len(new_code) > room:
            raise SystemExit('new code %d bytes, the saved string holds %d: shorten it, or add the room in the editor'
                             % (len(new_code), room))
        raw[at:at + len(code)] = (new_code + ' ' * (room - len(new_code))).encode('latin-1')
        changed.append(('code', title, new_code))
    if sets:
        sc = scalars(d)
        missing = [k for k in sets if k not in sc]
        if missing:
            raise SystemExit('no stored scalar parameter %s' % missing)
        knobs = {'%s#%s' % (k, o): (o, 'DefaultValue') for k in sets for o in sc[k]}
        where = locate(d, raw, knobs)
        for kn, loc in where.items():
            if loc is None:
                raise SystemExit('%s is at its engine default (not serialized): set it once in the editor' % kn)
            raw[loc[0]:loc[0] + 4] = struct.pack('<f', sets[kn.split('#')[0]])
        print('  copies set:', ', '.join('%s x%d' % (k, len(sc[k])) for k in sets))
    if not changed and not sets:
        print('nothing to do: give --list, --show, --code or --set')
        return 2
    old_id, _ = renew(raw, d, asset)
    print('  StateId renewed (was %s)' % old_id)
    backup(asset, not no_backup)
    with open(asset, 'wb') as fh:
        fh.write(bytes(raw))
    d2 = dump(asset, 'sdk_code_patch')
    with open(asset, 'rb') as fh:
        raw2 = bytearray(fh.read())
    ok = len(d2.get('Exports') or []) == len(d.get('Exports') or [])
    for _, name, new in changed:
        c2, _ = code_at(raw2, one_custom(customs(d2), name))
        ok = ok and c2.rstrip() == new
    if sets:
        after = locate(d2, raw2, {'%s#%s' % (k, o): (o, 'DefaultValue') for k in sets for o in scalars(d2).get(k, [])})
        ok = ok and len(after) == len(knobs) and \
            all(after[kn] is not None and f32(after[kn][1]) == f32(sets[kn.split('#')[0]]) for kn in after)
    print('written:', ', '.join(['code ' + n for _, n, _ in changed] + ['%s=%g' % kv for kv in sets.items()]), '| verified:', ok)
    if not ok:
        print('the read-back did not match: restore %s.bak before cooking' % asset if not no_backup else
              'the read-back did not match: do not cook this file', file=sys.stderr)
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except s2paths.S2PathError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
