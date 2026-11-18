"""Read Niagara module constants straight from an UNCOOKED UE 5.5 .uasset: no kit, no asset dump, no paste.

Walks the package header to the name, import and export tables, then decodes every NiagaraScript's
RapidIterationParameters and the system's ExposedParameters (a list of names with byte offsets, SortedParameterOffsets,
plus the packed values, ParameterData). Read-only: it opens one file for reading and prints.

usage: python niagara_constants.py <system or emitter .uasset> [filter substring]

One line per value: `Constants.<Emitter>.<Module>.<Input> [type] = value`, grouped by script. A constant appears once
per script that uses it (spawn, update, GPU compute). Limits: uncooked assets with file version UE5 1012 or newer; it
shows constants only, not what an input is linked to, not dynamic inputs and not expression text (copy those from the
editor, see references/niagara.md).
"""
import struct
import sys


def fstring(b, p):
    (n,) = struct.unpack_from('<i', b, p)
    p += 4
    if n == 0:
        return '', p
    if n < 0:
        return b[p:p - 2 * n - 2].decode('utf-16-le', 'replace'), p - 2 * n
    return b[p:p + n - 1].decode('latin-1', 'replace'), p + n


class Package:
    def __init__(self, raw):
        self.raw = raw
        tag, legacy, _ue3, _ue4, ue5, _lic = struct.unpack_from('<Iiiiii', raw, 0)
        if tag != 0x9E2A83C1:
            raise SystemExit('not a UE package (bad tag)')
        if ue5 < 1012:
            raise SystemExit('file version UE5 %d is older than 1012 (complete type names): not supported' % ue5)
        p = 24
        (custom,) = struct.unpack_from('<i', raw, p)
        p += 4 + custom * 20
        p += 4                                   # total header size
        _folder, p = fstring(raw, p)
        p += 4                                   # package flags
        name_count, name_off = struct.unpack_from('<ii', raw, p)
        p += 8
        p += 8                                   # soft object paths count, offset
        _loc, p = fstring(raw, p)
        p += 8                                   # gatherable text count, offset
        exp_count, exp_off = struct.unpack_from('<ii', raw, p)
        p += 8
        imp_count, imp_off = struct.unpack_from('<ii', raw, p)
        for label, cnt, off in (('name', name_count, name_off), ('export', exp_count, exp_off), ('import', imp_count, imp_off)):
            if not (0 < cnt < 5_000_000 and 0 < off < len(raw)):
                raise SystemExit('implausible %s table (count %d, offset %d): header layout differs' % (label, cnt, off))
        self.names = []
        q = name_off
        for _ in range(name_count):
            s, q = fstring(raw, q)
            self.names.append(s)
            q += 4                               # two 16-bit hashes
        self.imports = []
        for i in range(imp_count):
            self.imports.append(self.fname(raw, imp_off + i * 40 + 20))
        self.exports = []
        for i in range(exp_count):
            e = exp_off + i * 112
            cls, _sup, _tpl, outer = struct.unpack_from('<iiii', raw, e)
            size, off = struct.unpack_from('<qq', raw, e + 28)
            self.exports.append({'class': cls, 'outer': outer, 'name': self.fname(raw, e + 16), 'size': size, 'off': off})

    def fname(self, b, p):
        idx, num = struct.unpack_from('<II', b, p)
        s = self.names[idx] if idx < len(self.names) else '#%d' % idx
        return '%s_%d' % (s, num - 1) if num else s

    def class_name(self, idx):
        if idx < 0:
            return self.imports[-idx - 1]
        if idx > 0:
            return self.exports[idx - 1]['name']
        return None

    def path(self, i):
        parts = []
        while i > 0:
            e = self.exports[i - 1]
            parts.append(e['name'])
            i = e['outer']
        return '/'.join(reversed(parts))


def read_tag(pkg, b, p):
    """One UE 5.5 property tag. Returns (name or None, type name, size, value start)."""
    name = pkg.fname(b, p)
    p += 8
    if name == 'None':
        return None, None, 0, p
    type_name = None
    remaining = 1
    while remaining:
        node = pkg.fname(b, p)
        (inner,) = struct.unpack_from('<i', b, p + 8)
        p += 12
        if type_name is None:
            type_name = node
        remaining += inner - 1
    size, flags = struct.unpack_from('<IB', b, p)
    p += 5
    if flags & 1:
        p += 4                                   # array index
    if flags & 2:
        p += 16                                  # property guid
    return name, type_name, size, p


def fmt(typ, data):
    t = (typ or '').lower()

    def fl(k):
        return struct.unpack_from('<' + 'f' * k, data, 0)
    try:
        if t in ('niagarafloat', 'float'):
            return '%.6g' % fl(1)
        if t in ('niagaraint32', 'int32'):
            return str(struct.unpack_from('<i', data, 0)[0])
        if t == 'niagarabool':
            return str(struct.unpack_from('<i', data, 0)[0] != 0)
        if t in ('vector2f', 'vector2d', 'niagaravector2'):
            return '(%.6g, %.6g)' % fl(2)
        if t in ('vector3f', 'vector', 'niagaraposition', 'niagaravector3'):
            return '(%.6g, %.6g, %.6g)' % fl(3)
        if t in ('vector4f', 'vector4', 'linearcolor', 'quat4f', 'quat'):
            return '(%.6g, %.6g, %.6g, %.6g)' % fl(4)
        if t == 'niagaramatrix':
            return 'matrix'
        if len(data) == 4:
            return 'int %d / %.6g' % (struct.unpack_from('<i', data, 0)[0], fl(1)[0])
    except struct.error as ex:
        return '? %s' % ex
    return data.hex()


def read_store(pkg, b, p, end):
    """Tagged properties of one FNiagaraParameterStore between p and end."""
    offsets, pdata = [], b''
    while p < end:
        name, _typ, size, val = read_tag(pkg, b, p)
        if name is None:
            break
        if name == 'SortedParameterOffsets':
            (count,) = struct.unpack_from('<i', b, val)
            q = val + 4
            for _ in range(count):
                var = pkg.fname(b, q)
                q += 8
                typ = None
                while True:
                    n2, _t2, s2, v2 = read_tag(pkg, b, q)
                    if n2 is None:
                        q = v2
                        break
                    if n2 == 'ClassStructOrEnum' and s2 == 4:
                        (obj,) = struct.unpack_from('<i', b, v2)
                        typ = pkg.class_name(obj)
                    q = v2 + s2
                (off,) = struct.unpack_from('<i', b, q)
                q += 4
                offsets.append((var, off, typ))
        elif name == 'ParameterData':
            (count,) = struct.unpack_from('<i', b, val)
            pdata = b[val + 4:val + 4 + count]
        p = val + size
    rows = sorted(offsets, key=lambda r: r[1] if r[1] >= 0 else 1 << 30)
    out = []
    for i, (var, off, typ) in enumerate(rows):
        if off < 0:
            out.append((var, typ, '(DI/object)'))
            continue
        nxt = len(pdata)
        for j in range(i + 1, len(rows)):
            if rows[j][1] > off:
                nxt = rows[j][1]
                break
        out.append((var, typ, fmt(typ, pdata[off:nxt])))
    return out


def main(path, flt=None):
    raw = open(path, 'rb').read()
    pkg = Package(raw)
    for idx, e in enumerate(pkg.exports, 1):
        cname = pkg.class_name(e['class'])
        if cname not in ('NiagaraScript', 'NiagaraSystem'):
            continue
        b = raw[e['off']:e['off'] + e['size']]
        pname = 'RapidIterationParameters' if cname == 'NiagaraScript' else 'ExposedParameters'
        if pname not in pkg.names:
            continue
        pat = struct.pack('<II', pkg.names.index(pname), 0)
        p = b.find(pat)
        if p < 0:
            continue
        _n, _t, size, val = read_tag(pkg, b, p)
        rows = read_store(pkg, b, val, val + size)
        if flt:
            rows = [r for r in rows if flt.lower() in r[0].lower()]
        if not rows:
            continue
        print('== %s  (%d params)' % (pkg.path(idx), len(rows)))
        for var, typ, value in rows:
            print('   %s [%s] = %s' % (var, typ, value))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
