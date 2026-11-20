"""Compact, token-efficient summary of any .uasset (via uasset-dump) or existing UAssetAPI JSON.

Stages a temporary copy before invoking uasset-dump so it works safely even if the Zone Kit
editor holds a lock on the original asset, never writes huge raw JSON to stdout, and extracts
only structural imports, Material Instance parameters, Curve keys (with cubic-tangent flags),
or Material parameters and Custom HLSL nodes.

    python uasset_summary.py <file.uasset|file.json> [--material] [--ver VER_UE5_5] [--json]

Needs tools/uasset-dump built (see s2paths.py) when reading a .uasset; reads .json directly
without external tools. Pure stdlib.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2paths

SKIP_EXPORTS = {
    'MetaData',
    'SceneThumbnailInfoWithPrimitive',
    'AssetImportData',
    'MaterialGraph',
    'EdGraph',
    'MaterialGraphSchema',
}
SKIP_MAT_PROPS = {
    'StateId',
    'LightingGuid',
    'Expressions',
    'EditorComments',
    'ParameterGroupData',
    'MaterialExpressionEditorX',
    'MaterialExpressionEditorY',
    'MaterialExpressionGuid',
    'ExpressionGUID',
}
MAT_ROOT_KEYS = (
    'BlendMode',
    'ShadingModel',
    'TranslucencyLightingMode',
    'TranslucencyPass',
    'TwoSided',
    'bUseMaterialAttributes',
    'bUsesDistortion',
    'bEnableResponsiveAA',
    'RefractionMethod',
)


def _get_obj_name(data, idx):
    if not isinstance(idx, int):
        return str(idx)
    if idx < 0:
        imports = data.get('Imports') or []
        i = -idx - 1
        return imports[i].get('ObjectName', str(idx)) if 0 <= i < len(imports) else str(idx)
    if idx > 0:
        exports = data.get('Exports') or []
        i = idx - 1
        return exports[i].get('ObjectName', str(idx)) if 0 <= i < len(exports) else str(idx)
    return 'None'


def _float(val, default=0.0):
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return default
    return default


def load_uasset_json(path, ver='VER_UE5_5'):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise SystemExit('no such file: %s' % path)
    if path.lower().endswith('.json'):
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)

    exe = s2paths.uasset_dump()
    if not os.path.isfile(exe):
        raise s2paths.S2PathError('uasset-dump not found at %s (build tools/uasset-dump, see s2paths.py)' % exe)

    tmp_dir = os.path.join(s2paths.work_dir(), 'uasset_summary')
    os.makedirs(tmp_dir, exist_ok=True)
    tag = hashlib.sha256(path.encode('utf-8')).hexdigest()[:12]
    stem = os.path.basename(path)
    copy_uasset = os.path.join(tmp_dir, '%s_%s' % (tag, stem))
    out_json = copy_uasset + '.json'
    uexp_src = os.path.splitext(path)[0] + '.uexp'
    copy_uexp = os.path.splitext(copy_uasset)[0] + '.uexp'

    try:
        shutil.copy2(path, copy_uasset)
        if os.path.isfile(uexp_src):
            shutil.copy2(uexp_src, copy_uexp)
        r = subprocess.run([exe, copy_uasset, out_json, ver], capture_output=True, text=True, errors='replace', timeout=60)
        if r.returncode != 0 or not os.path.isfile(out_json) or os.path.getsize(out_json) == 0:
            msg = (r.stderr or r.stdout or '').strip()[-500:]
            raise SystemExit('uasset-dump failed on %s (exit %s): %s' % (path, r.returncode, msg))
        with open(out_json, encoding='utf-8') as fh:
            return json.load(fh)
    finally:
        for tmp_f in (copy_uasset, copy_uexp, out_json):
            if os.path.isfile(tmp_f):
                try:
                    os.remove(tmp_f)
                except OSError:
                    pass


def _extract_curve_tracks(exp):
    tracks = {}

    def walk(node, out):
        if isinstance(node, dict):
            if 'RichCurveKeyPropertyData' in str(node.get('$type', '')):
                v = node.get('Value')
                if isinstance(v, dict):
                    out.append({
                        't': _float(v.get('Time', 0.0)),
                        'v': _float(v.get('Value', 0.0)),
                        'mode': str(v.get('InterpMode', '')),
                        'at': _float(v.get('ArriveTangent', 0.0)),
                        'atw': _float(v.get('ArriveTangentWeight', 0.0)),
                        'lt': _float(v.get('LeaveTangent', 0.0)),
                        'ltw': _float(v.get('LeaveTangentWeight', 0.0)),
                    })
                return
            for sub in node.values():
                walk(sub, out)
        elif isinstance(node, list):
            for item in node:
                walk(item, out)

    for prop in exp.get('Data') or []:
        if not isinstance(prop, dict):
            continue
        pname = prop.get('Name', 'Curve')
        aidx = prop.get('ArrayIndex', 0)
        label = '%s[%d]' % (pname, aidx) if pname == 'ColorCurves' else pname
        keys = []
        walk(prop, keys)
        if keys:
            tracks[label] = keys
    return tracks


def _param_name(sub_list):
    for sub in sub_list:
        if not isinstance(sub, dict):
            continue
        if sub.get('Name') == 'ParameterInfo':
            for p in sub.get('Value') or []:
                if isinstance(p, dict) and p.get('Name') == 'Name':
                    return str(p.get('Value', ''))
    return ''


def _extract_mi_params(exp, data):
    scalars, vectors, textures, switches = [], [], [], []
    for prop in exp.get('Data') or []:
        if not isinstance(prop, dict):
            continue
        pname = prop.get('Name')
        if pname == 'ScalarParameterValues':
            for elem in prop.get('Value') or []:
                subs = elem.get('Value') or [] if isinstance(elem, dict) else []
                k = _param_name(subs)
                val = next((_float(s.get('Value', 0.0)) for s in subs if isinstance(s, dict) and s.get('Name') == 'ParameterValue'), None)
                if k:
                    scalars.append({'name': k, 'value': val})
        elif pname == 'VectorParameterValues':
            for elem in prop.get('Value') or []:
                subs = elem.get('Value') or [] if isinstance(elem, dict) else []
                k = _param_name(subs)
                val = None
                for s in subs:
                    if isinstance(s, dict) and s.get('Name') == 'ParameterValue':
                        inner = s.get('Value')
                        if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                            c = inner[0].get('Value')
                            if isinstance(c, dict):
                                val = [_float(c.get(ch, 0.0)) for ch in 'RGBA']
                if k and val is not None:
                    vectors.append({'name': k, 'value': val})
        elif pname == 'TextureParameterValues':
            for elem in prop.get('Value') or []:
                subs = elem.get('Value') or [] if isinstance(elem, dict) else []
                k = _param_name(subs)
                val = next((_get_obj_name(data, s.get('Value', 0)) for s in subs if isinstance(s, dict) and s.get('Name') == 'ParameterValue'), None)
                if k:
                    textures.append({'name': k, 'value': val})
        elif pname in ('StaticParameters', 'StaticParametersRuntime'):
            for sub in prop.get('Value') or []:
                if isinstance(sub, dict) and sub.get('Name') == 'StaticSwitchParameters':
                    for elem in sub.get('Value') or []:
                        subs = elem.get('Value') or [] if isinstance(elem, dict) else []
                        k = _param_name(subs)
                        val = next((s.get('Value') for s in subs if isinstance(s, dict) and s.get('Name') == 'Value'), None)
                        if k:
                            switches.append({'name': k, 'value': bool(val)})
    return scalars, vectors, textures, switches


def summarize_asset(path, data, material_mode=False):
    imports = data.get('Imports') or []
    exports = data.get('Exports') or []

    imp_by_cls = {}
    for imp in imports:
        if not isinstance(imp, dict):
            continue
        cls = imp.get('ClassName', 'Unknown')
        if cls in ('Package', 'Class', 'ScriptStruct'):
            continue
        imp_by_cls.setdefault(cls, []).append(str(imp.get('ObjectName', '')))

    summary = {
        'file': os.path.basename(path),
        'import_count': len(imports),
        'export_count': len(exports),
        'imports': imp_by_cls,
        'exports': [],
        'expression_count': 0,
        'material': None,
    }

    mat_info = {
        'properties': {},
        'textures': imp_by_cls.get('Texture2D', []),
        'functions': imp_by_cls.get('MaterialFunction', []),
        'mpcs': imp_by_cls.get('MaterialParameterCollection', []),
        'scalars': [],
        'vectors': [],
        'switches': [],
        'collections': [],
        'custom_nodes': [],
    }

    for exp in exports:
        if not isinstance(exp, dict):
            continue
        cls = _get_obj_name(data, exp.get('ClassIndex', 0))
        obj = str(exp.get('ObjectName', ''))

        if cls.startswith('MaterialExpression'):
            summary['expression_count'] += 1
            if material_mode:
                props = {p.get('Name'): p for p in (exp.get('Data') or []) if isinstance(p, dict) and p.get('Name')}
                if 'ScalarParameter' in cls or 'VectorParameter' in cls or 'StaticSwitchParameter' in cls:
                    pname = props.get('ParameterName', {}).get('Value')
                    dval = props.get('DefaultValue', {}).get('Value')
                    if pname:
                        entry = {'name': str(pname), 'default': dval}
                        if 'Scalar' in cls:
                            mat_info['scalars'].append(entry)
                        elif 'Vector' in cls:
                            mat_info['vectors'].append(entry)
                        else:
                            mat_info['switches'].append(entry)
                elif 'CollectionParameter' in cls:
                    c_idx = props.get('Collection', {}).get('Value', 0)
                    p_name = props.get('ParameterName', {}).get('Value', '')
                    mat_info['collections'].append({'collection': _get_obj_name(data, c_idx), 'param': str(p_name)})
                elif cls == 'MaterialExpressionCustom':
                    code = str(props.get('Code', {}).get('Value') or '')
                    desc = str(props.get('Description', {}).get('Value') or obj)
                    mat_info['custom_nodes'].append({'node': obj, 'desc': desc, 'lines': len(code.splitlines())})
            continue

        if cls in SKIP_EXPORTS:
            continue

        if cls == 'MaterialInstanceConstant':
            parent_idx = next((p.get('Value', 0) for p in (exp.get('Data') or []) if isinstance(p, dict) and p.get('Name') == 'Parent'), 0)
            scalars, vectors, textures, switches = _extract_mi_params(exp, data)
            summary['exports'].append({
                'class': cls,
                'name': obj,
                'parent': _get_obj_name(data, parent_idx),
                'scalars': scalars,
                'vectors': vectors,
                'textures': textures,
                'switches': switches,
            })
        elif cls in ('CurveFloat', 'CurveLinearColor', 'CurveVector'):
            tracks = _extract_curve_tracks(exp)
            summary['exports'].append({'class': cls, 'name': obj, 'tracks': tracks})
        elif cls == 'Material':
            mprops = {}
            for p in exp.get('Data') or []:
                if not isinstance(p, dict):
                    continue
                k = p.get('Name', '')
                if k in MAT_ROOT_KEYS:
                    val = p.get('Value') if p.get('Value') is not None else p.get('EnumValue')
                    mprops[k] = val
            mat_info['properties'] = mprops
            summary['exports'].append({'class': cls, 'name': obj, 'properties': mprops})
        else:
            simple = {}
            for p in exp.get('Data') or []:
                if not isinstance(p, dict):
                    continue
                k = p.get('Name', '')
                if not k or k in SKIP_MAT_PROPS:
                    continue
                val = p.get('Value') if p.get('Value') is not None else p.get('EnumValue')
                if isinstance(val, (int, float, str, bool)):
                    if isinstance(val, int) and not isinstance(val, bool) and 'ObjectPropertyData' in str(p.get('$type', '')):
                        simple[k] = '-> ' + _get_obj_name(data, val)
                    else:
                        simple[k] = val
            summary['exports'].append({'class': cls, 'name': obj, 'properties': simple})

    if material_mode:
        summary['material'] = mat_info
    return summary


def _fmt_num_or_raw(val):
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return '%.6g' % float(val)
    if isinstance(val, str):
        try:
            return '%.6g' % float(val)
        except ValueError:
            return val
    return val


def format_text(summary):
    lines = ['=== UASSET SUMMARY: %s (imports=%d, exports=%d) ===' % (
        summary['file'], summary['import_count'], summary['export_count']
    )]
    if summary['imports']:
        lines.append('Imports:')
        for cls, names in sorted(summary['imports'].items()):
            head = ', '.join(names[:10])
            tail = ' ... (+%d)' % (len(names) - 10) if len(names) > 10 else ''
            lines.append('  %s (%d): %s%s' % (cls, len(names), head, tail))

    for exp in summary['exports']:
        cls = exp['class']
        if cls == 'MaterialInstanceConstant':
            lines.append('  [%s] %s (Parent: %s)' % (cls, exp['name'], exp['parent']))
            if exp['scalars']:
                lines.append('    Scalars : ' + ', '.join(
                    '%s=%s' % (
                        s['name'],
                        ('%.4g' % s['value']) if isinstance(s['value'], (int, float)) and not isinstance(s['value'], bool) else 'None',
                    )
                    for s in exp['scalars']
                ))
            if exp['vectors']:
                lines.append('    Vectors : ' + ', '.join('%s=(%s)' % (v['name'], ','.join('%.3g' % x for x in v['value'])) for v in exp['vectors']))
            if exp['textures']:
                lines.append('    Textures: ' + ', '.join('%s=%s' % (t['name'], t['value']) for t in exp['textures']))
            if exp['switches']:
                lines.append('    Switches: ' + ', '.join('%s=%s' % (s['name'], s['value']) for s in exp['switches']))
        elif 'tracks' in exp:
            lines.append('  [%s] %s' % (cls, exp['name']))
            for tname, keys in exp['tracks'].items():
                prev = ', '.join('%.4g:%.4g' % (k['t'], k['v']) for k in keys[:10])
                if len(keys) > 10:
                    prev += ' ... (%d keys)' % len(keys)
                cubic_nonzero = sum(
                    1 for k in keys
                    if ('Cubic' in k['mode'] or k['mode'] == '2')
                    and any(abs(k[f]) > 1e-6 for f in ('at', 'atw', 'lt', 'ltw'))
                )
                warn = ' [WARN: %d cubic key(s) with non-zero tangents]' % cubic_nonzero if cubic_nonzero else ''
                lines.append('    %s: [%s]%s' % (tname, prev, warn))
        else:
            lines.append('  [%s] %s' % (cls, exp['name']))
            for k, v in list(exp.get('properties', {}).items())[:25]:
                lines.append('    %s: %s' % (k, v))

    if summary['expression_count'] and not summary['material']:
        lines.append('  [Material Graph] %d MaterialExpression nodes (re-run with --material for parameter/Custom summary)' % summary['expression_count'])

    mat = summary.get('material')
    if mat:
        lines.append('Material Overview (%d expression nodes):' % summary['expression_count'])
        if mat['properties']:
            lines.append('  Flags     : ' + ', '.join('%s=%s' % (k, v) for k, v in mat['properties'].items()))
        if mat['scalars']:
            lines.append('  Scalars   : ' + ', '.join('%s=%s' % (x['name'], _fmt_num_or_raw(x['default'])) for x in mat['scalars']))
        if mat['vectors']:
            lines.append('  Vectors   : ' + ', '.join(x['name'] for x in mat['vectors']))
        if mat['switches']:
            lines.append('  Switches  : ' + ', '.join('%s=%s' % (x['name'], x['default']) for x in mat['switches']))
        if mat['collections']:
            lines.append('  MPCs      : ' + ', '.join('%s.%s' % (x['collection'], x['param']) for x in mat['collections']))
        if mat['custom_nodes']:
            lines.append('  CustomHLSL: ' + ', '.join('%s (%s, %d lines)' % (x['node'], x['desc'], x['lines']) for x in mat['custom_nodes']))
    return '\n'.join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('path', help='path to .uasset or existing UAssetAPI .json')
    ap.add_argument('--material', action='store_true', help='include Material parameter and Custom node breakdown')
    ap.add_argument('--ver', default='VER_UE5_5', help='UE version passed to uasset-dump (default: VER_UE5_5)')
    ap.add_argument('--json', action='store_true', help='emit structured JSON summary')
    args = ap.parse_args(argv)

    data = load_uasset_json(args.path, ver=args.ver)
    summary = summarize_asset(args.path, data, material_mode=args.material)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_text(summary))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except s2paths.S2PathError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
