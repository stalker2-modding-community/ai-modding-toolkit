"""Decode, check and diff legacy (retoc to-legacy) UCurveFloat / UCurveLinearColor .uexp files.

    python decode_curves.py <curve.uexp> [more .uexp ...]        prints {file name: [curve keys ...]} as JSON
    python decode_curves.py --check <curve.uexp> [more .uexp ...] summaries + flags cubic keys with non-zero tangents
    python decode_curves.py --diff <vanilla> <mod>                compares two .uexp files or matching .uexp folders

Get the files with retoc (read-only on the game): retoc to-legacy --no-shaders -f Curves/<State> "<paks>" "<out folder>".
As a module: decode(path) -> list of curves, each a list of {t, v, at, atw, lt, ltw, mode} dicts; key_offsets(path) -> per
curve, the absolute byte offset of each key's Value float, for in-place edits; sample(keys, t) -> linear sample.

Layout: Unreal unversioned property serialization.
  - Top-level fragments: Unreal writes each as a little-endian uint16 (bits 0-6 skipped properties, bit 7 a zero mask
    follows, bit 8 last fragment, bits 9-15 values that follow). Read as big-endian words, as here: bit0 = last fragment,
    bits1-7 = values, bits8-14 = skipped (default) properties, bit15 = a zero mask follows the fragments.
    A CurveFloat has one FRichCurve value, a CurveLinearColor four (R,G,B,A);
    files written by other tools sometimes carry one extra trailing property, which is ignored.
  - Each FRichCurve value: its own fragments; if it declares one value, an int32 key count follows,
    then count x 27-byte keys (InterpMode, TangentMode, TangentWeightMode as bytes, then Time,
    Value, ArriveTangent, ArriveTangentWeight, LeaveTangent, LeaveTangentWeight as float32).
    A curve declaring zero values is empty (the game uses the default, 0).
  - File ends with the 4-byte package tag.
Read-only, no other tools needed.
"""
import struct, sys, json, os

KEY_SIZE = 27


def _frags(b, pos):
    frags = []
    while True:
        if pos + 2 > len(b):
            raise ValueError('ran out of data while reading property fragments at %d' % pos)
        f = int.from_bytes(b[pos:pos + 2], 'big')
        pos += 2
        frags.append(f)
        if f & 1:
            break
    values = sum((f >> 1) & 0x7f for f in frags)
    has_zero_mask = any((f >> 15) & 1 for f in frags)
    if has_zero_mask and values:
        pos += (values + 7) // 8
    return values, pos


def _parse(b):
    """Returns (curves, offsets). curves: list of key lists; offsets: list of lists of Value-float offsets."""
    n_props, pos = _frags(b, 0)
    curves, offsets = [], []
    end = len(b) - 4  # package tag
    for _ in range(min(n_props, 4)):
        if pos + 2 > end:
            break
        vals, pos = _frags(b, pos)
        if vals == 0:
            curves.append([])
            offsets.append([])
            continue
        if pos + 4 > len(b):
            raise ValueError('ran out of data before the key count at %d' % pos)
        count = struct.unpack_from('<i', b, pos)[0]
        pos += 4
        if count < 0 or pos + count * KEY_SIZE > end + 4:
            raise ValueError(f'bad key count {count} at {pos}')
        keys, offs = [], []
        for _k in range(count):
            im, tm, twm = b[pos], b[pos + 1], b[pos + 2]
            t, v, at, atw, lt, ltw = struct.unpack_from('<6f', b, pos + 3)
            keys.append({'t': round(t, 4), 'v': round(v, 6), 'at': at, 'atw': atw, 'lt': lt, 'ltw': ltw, 'mode': (im, tm, twm)})
            offs.append(pos + 3 + 4)  # Value float sits after 3 mode bytes and the Time float
            pos += KEY_SIZE
        if vals > 1:
            # Extra FRichCurve properties after Keys (DefaultValue etc.) have unknown size here; stop.
            curves.append(keys)
            offsets.append(offs)
            break
        curves.append(keys)
        offsets.append(offs)
    return curves, offsets


def decode(path):
    with open(path, 'rb') as fh:
        return _parse(fh.read())[0]


def key_offsets(path):
    with open(path, 'rb') as fh:
        return _parse(fh.read())[1]


def sample(keys, t):
    """Linear sample; vanilla lighting curves use linear interp with zero tangents."""
    if not keys:
        return None
    if t <= keys[0]['t']:
        return keys[0]['v']
    if t >= keys[-1]['t']:
        return keys[-1]['v']
    for a, c in zip(keys, keys[1:]):
        if a['t'] <= t <= c['t']:
            f = (t - a['t']) / (c['t'] - a['t']) if c['t'] != a['t'] else 0
            return a['v'] + f * (c['v'] - a['v'])


def _has_nonzero_cubic_tangent(k):
    return k['mode'][0] == 2 and any(abs(k[f]) > 1e-6 for f in ('at', 'atw', 'lt', 'ltw'))


def _channel_labels(n):
    return ('Value',) if n <= 1 else ('R', 'G', 'B', 'A')[:n]


def _check_files(paths):
    bad = 0
    for p in paths:
        if not os.path.isfile(p):
            print('no such file: %s' % p, file=sys.stderr)
            bad += 1
            continue
        try:
            channels = decode(p)
        except ValueError as e:
            print('%s: %s (not a curve .uexp in the expected layout?)' % (p, e), file=sys.stderr)
            bad += 1
            continue
        print('=== %s (%d channel(s)) ===' % (os.path.basename(p), len(channels)))
        labels = _channel_labels(len(channels))
        for idx, keys in enumerate(channels):
            lbl = labels[idx] if idx < len(labels) else ('Ch%d' % idx)
            if not keys:
                print('  %s: empty (0 keys, default 0)' % lbl)
                continue
            modes = {'linear': 0, 'const': 0, 'cubic': 0, 'other': 0}
            risky = []
            for k in keys:
                im = k['mode'][0]
                if im == 0:
                    modes['linear'] += 1
                elif im == 1:
                    modes['const'] += 1
                elif im == 2:
                    modes['cubic'] += 1
                else:
                    modes['other'] += 1
                if _has_nonzero_cubic_tangent(k):
                    risky.append(k['t'])
            span = '%.4g..%.4g' % (keys[0]['t'], keys[-1]['t'])
            mstr = ', '.join('%s=%d' % (mk, mv) for mk, mv in modes.items() if mv)
            print('  %s: %d key(s), t=[%s], modes={%s}' % (lbl, len(keys), span, mstr))
            if risky:
                preview = ', '.join('%.4g' % t for t in risky[:8])
                tail = ' ... (+%d)' % (len(risky) - 8) if len(risky) > 8 else ''
                print('    WARN %d cubic key(s) carry non-zero tangents at t=[%s%s] (zero tangents to prevent overshoot)'
                      % (len(risky), preview, tail))
    return 1 if bad else 0


def _diff_channels(label, v_keys, m_keys):
    deltas = []
    vi, mi = 0, 0
    vs = sorted(v_keys, key=lambda x: x['t'])
    ms = sorted(m_keys, key=lambda x: x['t'])
    while vi < len(vs) and mi < len(ms):
        vt, mt = vs[vi]['t'], ms[mi]['t']
        if abs(vt - mt) <= 1e-4:
            vk, mk = vs[vi], ms[mi]
            val_diff = abs(vk['v'] - mk['v']) > 1e-6
            tan_diff = any(abs(vk[f] - mk[f]) > 1e-6 for f in ('at', 'atw', 'lt', 'ltw'))
            mode_diff = vk['mode'] != mk['mode']
            if val_diff or tan_diff or mode_diff:
                warn = ' [WARN: non-zero cubic tangent]' if _has_nonzero_cubic_tangent(mk) else ''
                extra = []
                if mode_diff:
                    extra.append('mode %s->%s' % (vk['mode'], mk['mode']))
                if tan_diff:
                    extra.append('tangents changed')
                suffix = ' (%s)' % ', '.join(extra) if extra else ''
                deltas.append('  %s @ %.4g: %.6g -> %.6g%s%s' % (label, mt, vk['v'], mk['v'], suffix, warn))
            vi += 1
            mi += 1
        elif vt < mt:
            vk = vs[vi]
            deltas.append('  %s @ %.4g: REMOVED (was %.6g)' % (label, vk['t'], vk['v']))
            vi += 1
        else:
            mk = ms[mi]
            warn = ' [WARN: non-zero cubic tangent]' if _has_nonzero_cubic_tangent(mk) else ''
            deltas.append('  %s @ %.4g: ADDED %.6g%s' % (label, mk['t'], mk['v'], warn))
            mi += 1
    while vi < len(vs):
        vk = vs[vi]
        deltas.append('  %s @ %.4g: REMOVED (was %.6g)' % (label, vk['t'], vk['v']))
        vi += 1
    while mi < len(ms):
        mk = ms[mi]
        warn = ' [WARN: non-zero cubic tangent]' if _has_nonzero_cubic_tangent(mk) else ''
        deltas.append('  %s @ %.4g: ADDED %.6g%s' % (label, mk['t'], mk['v'], warn))
        mi += 1
    return deltas


def _diff_pair(vanilla_path, mod_path, label=None):
    v_ch = decode(vanilla_path)
    m_ch = decode(mod_path)
    n = max(len(v_ch), len(m_ch))
    labels = _channel_labels(n)
    lines = []
    for idx in range(n):
        lbl = labels[idx] if idx < len(labels) else ('Ch%d' % idx)
        vk = v_ch[idx] if idx < len(v_ch) else []
        mk = m_ch[idx] if idx < len(m_ch) else []
        lines.extend(_diff_channels(lbl, vk, mk))
    if lines:
        print('DIFF %s (%d change(s)):' % (label or os.path.basename(mod_path), len(lines)))
        for ln in lines:
            print(ln)
    else:
        print('SAME %s (0 changes)' % (label or os.path.basename(mod_path)))
    return bool(lines)


def _collect_uexp_map(root):
    found = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith('.uexp'):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace('\\', '/')
                found[rel.lower()] = (rel, os.path.join(dirpath, fn))
    return found


def _diff_targets(vanilla_target, mod_target):
    if os.path.isfile(vanilla_target) and os.path.isfile(mod_target):
        try:
            _diff_pair(vanilla_target, mod_target)
            return 0
        except ValueError as e:
            print('diff failed: %s' % e, file=sys.stderr)
            return 1
    if os.path.isdir(vanilla_target) and os.path.isdir(mod_target):
        v_map = _collect_uexp_map(vanilla_target)
        m_map = _collect_uexp_map(mod_target)
        if not m_map:
            print('no .uexp files found in %s' % mod_target, file=sys.stderr)
            return 1
        bad, changed, matched = 0, 0, 0
        for key in sorted(m_map):
            rel, m_file = m_map[key]
            if key not in v_map:
                by_name = [v for v in v_map.values() if os.path.basename(v[0]).lower() == os.path.basename(rel).lower()]
                if len(by_name) == 1:
                    v_file = by_name[0][1]
                else:
                    print('ONLY_IN_MOD %s (no matching baseline in %s)' % (rel, vanilla_target))
                    continue
            else:
                v_file = v_map[key][1]
            matched += 1
            try:
                if _diff_pair(v_file, m_file, label=rel):
                    changed += 1
            except ValueError as e:
                print('ERR %s: %s' % (rel, e), file=sys.stderr)
                bad += 1
        print('summary: %d matched file(s), %d changed, %d error(s)' % (matched, changed, bad))
        return 1 if bad else 0
    print('--diff requires two .uexp files or two directories', file=sys.stderr)
    return 2


def main(argv):
    if not argv or '-h' in argv or '--help' in argv:
        print(__doc__)
        return 0 if argv else 2
    if argv[0] == '--check':
        if len(argv) < 2:
            print('--check requires at least one .uexp file', file=sys.stderr)
            return 2
        return _check_files(argv[1:])
    if argv[0] == '--diff':
        if len(argv) != 3:
            print('usage: decode_curves.py --diff <vanilla> <mod>', file=sys.stderr)
            return 2
        return _diff_targets(argv[1], argv[2])
    out, bad = {}, 0
    for p in argv:
        if not os.path.isfile(p):
            print('no such file: %s' % p, file=sys.stderr)
            bad += 1
            continue
        try:
            out[os.path.basename(p)] = decode(p)
        except ValueError as e:
            print('%s: %s (not a curve .uexp in the expected layout?)' % (p, e), file=sys.stderr)
            bad += 1
    print(json.dumps(out))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
