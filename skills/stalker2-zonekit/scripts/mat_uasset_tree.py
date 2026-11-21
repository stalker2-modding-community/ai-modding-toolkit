r"""First look at a material's wiring as formulas, straight from a saved .uasset (no editor, no graph copy needed).

It reads the links from the raw export bytes (an ExpressionInput's source index sits 49 bytes after its name tag, a
CustomInput's 57 bytes after its InputName), walks back from every root pin (including MaterialAttributes inputs on
bUseMaterialAttributes materials) and from a custom output node (Volumetric
Advanced Output, Single Layer Water Output), and prints each expression once (shared sub-expressions as @N), with Custom
node code, parameter names and defaults. It is a byte-pattern reader and can miss links: for the real wiring copy the
graph out of the material editor as text and read it with mat_t3d.py, which is the ground truth.

    python mat_uasset_tree.py <material.uasset> [--old] > out.txt

--old: GSC's uncooked kit assets saved by their older editor (pre-5.5 property tags). The asset is read through a copy in
the work folder (the editor keeps the file open); the original is never changed. Needs uasset-dump (see s2paths.py).
"""
import os, sys, json, shutil, struct, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2paths

KINDS = {'ExpressionInput', 'MaterialAttributesInput', 'ScalarMaterialInput', 'ColorMaterialInput', 'VectorMaterialInput', 'Vector2MaterialInput'}
SKIP_PROPS = {'MaterialExpressionEditorX', 'MaterialExpressionEditorY', 'MaterialExpressionGuid', 'ExpressionGUID', 'Material', 'Inputs',
              'Code', 'Description', 'Outputs', 'bRealtimePreview', 'bCollapsed', 'SortPriority', 'Desc'}


def load(asset):
    exe = s2paths.uasset_dump()
    if not os.path.isfile(exe):
        raise s2paths.S2PathError('uasset-dump not found at %s (build tools/uasset-dump, see s2paths.py)' % exe)
    tmp = os.path.join(s2paths.work_dir(), 'mat_uasset_tree')
    os.makedirs(tmp, exist_ok=True)
    copy = os.path.join(tmp, os.path.basename(asset))
    shutil.copyfile(asset, copy)
    out = copy + '.json'
    if os.path.exists(out):
        os.remove(out)
    r = subprocess.run([exe, copy, out, 'VER_UE5_5'], capture_output=True, text=True, errors='replace')
    if r.returncode or not os.path.isfile(out):
        raise SystemExit('uasset-dump failed on %s (exit %s): %s' % (asset, r.returncode, (r.stdout + r.stderr).strip()[-800:]))
    with open(out, encoding='utf-8') as fh:
        d = json.load(fh)
    with open(copy, 'rb') as fh:
        return d, fh.read()


def short(v):
    if isinstance(v, list) and v and isinstance(v[0], dict) and 'Value' in v[0]:
        c = v[0]['Value']
        if isinstance(c, dict) and 'R' in c:
            return '(%s)' % ', '.join('%.4g' % float(c.get(k, 0) or 0) for k in 'RGBA')
    if isinstance(v, float):
        return '%.6g' % v
    if isinstance(v, (int, str, bool)) or v is None:
        return str(v)
    return json.dumps(v)[:60]


OLD = '--old' in sys.argv     # GSC's uncooked kit assets saved by their older editor (ObjectVersionUE5 ADD_SOFTOBJECTPATH_LIST)


def main():
    args = [x for x in sys.argv[1:] if x != '--old']
    if len(args) != 1 or args[0] in ('-h', '--help'):
        print(__doc__)
        return 0 if args[:1] in (['-h'], ['--help']) else 2
    asset = args[0]
    if not os.path.isfile(asset):
        raise SystemExit('no such file: %s' % asset)
    sys.setrecursionlimit(20000)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    d, raw = load(asset)
    names, ex = d.get('NameMap') or [], d.get('Exports') or []
    N = len(names)
    P = [{q['Name']: q.get('Value') for q in e.get('Data') or [] if isinstance(q, dict) and 'Name' in q} for e in ex]

    def links(k):
        e = ex[k]
        blob = raw[e['SerialOffset']:e['SerialOffset'] + e['SerialSize']]
        out = []
        for pos in range(0, len(blob) - 60):
            n, z, n2, z2 = struct.unpack_from('<iiii', blob, pos)
            if z or z2 or not (0 <= n < N and 0 <= n2 < N) or names[n2] != 'StructProperty':
                continue
            n3 = struct.unpack_from('<i', blob, pos + (24 if OLD else 20))[0]   # --old: pre-5.5 tag (size + array index before the struct name)
            if 0 <= n3 < N and names[n3] in KINDS:
                v = struct.unpack_from('<i', blob, pos + 49)[0]
                if v:
                    out.append((names[n], v))
        # Custom inputs: walk every InputName tag (UE 5.5 tag: name 8, type 8, inner count 4, size 4, flags 1 -> the value FName at
        # +25), the input's expression index 57 bytes after that value. Searching only for the FIRST occurrence of an input's
        # name would miss inputs whose name also occurs earlier in the export.
        if P[k].get('Inputs') and 'InputName' in names:
            tag, pos = struct.pack('<ii', names.index('InputName'), 0), 0
            while (i := blob.find(tag, pos)) >= 0:
                if i + 86 > len(blob):
                    break
                vi = struct.unpack_from('<i', blob, i + 25)[0]
                v = struct.unpack_from('<i', blob, i + 82)[0]
                if 0 <= vi < N and v:
                    out.append((names[vi], v))
                pos = i + 8
        return out

    L = [links(k) for k in range(len(ex))]
    users = {}
    for k in range(len(ex)):
        for _, v in L[k]:
            users[v] = users.get(v, 0) + 1
    shared, printed, lines = {}, set(), []

    def name(v):
        e = ex[v - 1]
        cls = e['ObjectName'].replace('MaterialExpression', '')
        p = P[v - 1]
        tag = p.get('ParameterName') or p.get('Description')
        def is_link(x):
            return isinstance(x, list) and x and isinstance(x[0], dict) and 'Input' in str(x[0].get('$type', ''))
        props = ', '.join('%s=%s' % (k, short(x)) for k, x in p.items() if k not in SKIP_PROPS and k not in ('ParameterName',) and not is_link(x))
        return '%s%s%s' % (cls, ' "%s"' % tag if isinstance(tag, str) and tag else '', ' [%s]' % props if props else '')

    stack = set()

    def expr(v, depth=0):
        if not 1 <= v <= len(ex):
            return '(import %d)' % v
        if v in shared:
            return '@%d' % shared[v]
        if v in stack:
            return '(cycle: %s)' % ex[v - 1]['ObjectName']
        ins = L[v - 1]
        decl = P[v - 1].get('Declaration')
        if 'NamedRerouteUsage' in ex[v - 1]['ObjectName'] and isinstance(decl, int) and decl > 0:   # a named reroute usage reads its declaration
            stack.add(v)
            try:
                return expr(decl, depth)
            finally:
                stack.discard(v)
        if 'Reroute' in ex[v - 1]['ObjectName'] and ins:          # reroutes are wires: pass through
            stack.add(v)
            try:
                return expr(ins[0][1], depth)
            finally:
                stack.discard(v)
        stack.add(v)
        body = name(v)
        code = P[v - 1].get('Code')
        if ins:
            body += '(' + ', '.join('%s=%s' % (pin, expr(s, depth + 1)) for pin, s in ins if pin != 'Input' or 'Custom' not in ex[v - 1]['ObjectName']) + ')'
        if code:
            body += ' {code: %s}' % code.replace('\r\n', ' | ').replace('\n', ' | ')
        stack.discard(v)                                          # only a true loop back into the current path is a cycle
        if (users.get(v, 0) > 1 or 'NamedReroute' in ex[v - 1]['ObjectName']) and len(body) > 60:
            shared[v] = len(shared) + 1
            lines.append('@%d = %s' % (shared[v], body))
            return '@%d' % shared[v]
        return body

    roots = [k for k in range(len(ex)) if ex[k]['ObjectName'].endswith('EditorOnlyData')]
    advanced = [k for k in range(len(ex)) if 'VolumetricAdvancedMaterialOutput' in ex[k]['ObjectName']
                or 'SingleLayerWaterMaterialOutput' in ex[k]['ObjectName']]     # custom output nodes (clouds, Single Layer Water)
    out = []
    for k in roots + advanced:
        seen_pins = set()
        for pin, v in L[k]:
            # CustomizedUVs is a fixed array on MaterialEditorOnlyData; the +49 byte scan misreads its slots as false links.
            if pin in seen_pins or (k in roots and pin == 'CustomizedUVs'):
                continue
            seen_pins.add(pin)
            out.append('%s.%s = %s' % ('ROOT' if k in roots else 'ADVANCED', pin, expr(v)))
        if k in advanced:
            out.append('ADVANCED props: ' + ', '.join('%s=%s' % (a, short(b)) for a, b in P[k].items() if a not in SKIP_PROPS and not (isinstance(b, list) and b and isinstance(b[0], dict) and 'Input' in str(b[0].get('$type', '')))))
    print('# %s: %d exports; shared sub-expressions first, then the outputs\n' % (os.path.basename(asset), len(ex)))
    print('\n\n'.join(lines + out))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except s2paths.S2PathError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
