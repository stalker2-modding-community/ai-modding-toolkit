"""Fast pure-Python binary UE5 .uasset header and .cfg / .cfg_patch folder scanner.

Reads only each .uasset's package header (FPackageFileSummary, NameMap, ImportMap, ExportMap)
with no editor and no uasset-dump needed, identifying primary asset classes, key MPC / M / MI / NS
references, and cross-mod package dependencies alongside loose .cfg / .cfg_patch* files.

    python uasset_scan.py [<dir>] [--filter <substr>] [--limit 50] [--cross-mod <mod>] [--json]

Read-only. Pure stdlib. Works on uncooked UE5 packages (fv5 1000..2000).
"""
import argparse
import json
import os
import struct
import sys

UE_PACKAGE_MAGIC = 0x9E2A83C1
SKIP_DIRS = {'.git', 'Intermediate', 'Saved', '__pycache__', 'node_modules', '.ai'}
BUILTIN_ROOTS = {
    'Game', 'Engine', 'Script', 'Temp', 'Memory', 'Transient',
    'Niagara', 'NiagaraFluids', 'NiagaraUIRenderer', 'NiagaraSimCaching',
    'ControlRig', 'RigVM', 'ChaosNiagara', 'EnhancedInput', 'CommonUI',
    'Wwise', 'WwiseNiagara', 'WwiseSoundEngine', 'AkAudio',
    'ModBase', 'ModKit', 'S2_BaseGame',
}

CLASS_PRIORITY = {
    'MaterialInstanceConstant': 100,
    'WeatherPresetDataAsset': 95,
    'ModWorldSubsystemDataAsset': 95,
    'ActorReplacementDataAsset': 95,
    'ModActorPatchesDataAsset': 95,
    'GameFeatureData': 92,
    'NiagaraSystem': 90,
    'CurveLinearColor': 88,
    'CurveFloat': 85,
    'CurveVector': 85,
    'GSCDataTable': 82,
    'CompositeDataTable': 82,
    'DataTable': 82,
    'MaterialParameterCollection': 80,
    'BlueprintGeneratedClass': 78,
    'Blueprint': 78,
    'Material': 75,
    'MaterialFunction': 75,
    'UserDefinedStruct': 75,
    'UserDefinedEnum': 75,
    'Texture2D': 70,
    'VolumeTexture': 70,
    'TextureCube': 70,
    'TextureRenderTarget2D': 70,
    'StaticMesh': 70,
    'SkeletalMesh': 70,
    'AnimSequence': 70,
    'AnimMontage': 70,
    'DataAsset': 65,
}
LOW_PRIORITY_CLASSES = {
    'AssetImportData',
    'MetaData',
    'EdGraph',
    'MaterialGraph',
    'MaterialGraphSchema',
    'BodySetup',
    'ThumbnailInfo',
    'SceneThumbnailInfo',
    'SceneThumbnailInfoWithPrimitive',
}


def _read_fstring(buf, pos):
    if pos + 4 > len(buf):
        raise ValueError('truncated FString length')
    (n,) = struct.unpack_from('<i', buf, pos)
    pos += 4
    if n == 0:
        return '', pos
    if n > 0:
        if n > 1_048_576 or pos + n > len(buf):
            raise ValueError('invalid ANSI FString length %d' % n)
        return buf[pos:pos + n - 1].decode('utf-8', 'replace'), pos + n
    chars = -n
    byte_len = chars * 2
    if chars > 524_288 or pos + byte_len > len(buf):
        raise ValueError('invalid UTF-16 FString length %d' % chars)
    s = buf[pos:pos + byte_len - 2].decode('utf-16-le', 'replace')
    return s, pos + byte_len


def inspect_uasset_header(path, self_mod=''):
    """Parse binary FPackageFileSummary, NameMap, ImportMap and ExportMap from a .uasset file."""
    with open(path, 'rb') as fh:
        buf = bytearray(fh.read(4096))
        if len(buf) < 32:
            raise ValueError('file too small for FPackageFileSummary')
        magic, _legacy, _ue3, _ue4, fv5, _lic = struct.unpack_from('<Iiiiii', buf, 0)
        if magic != UE_PACKAGE_MAGIC:
            raise ValueError('bad magic 0x%08X' % magic)
        if not (1000 <= fv5 <= 2000):
            raise ValueError('unsupported fv5=%d' % fv5)
        (cv_count,) = struct.unpack_from('<i', buf, 24)
        if not (0 <= cv_count <= 4096):
            raise ValueError('invalid custom version count %d' % cv_count)
        p = 28 + cv_count * 20
        if p + 4 > len(buf):
            buf.extend(fh.read(p + 4 - len(buf)))
        if p + 4 > len(buf):
            raise ValueError('truncated before TotalHeaderSize')
        (total_header_size,) = struct.unpack_from('<i', buf, p)
        p += 4
        if total_header_size <= p or total_header_size > 64 * 1024 * 1024:
            raise ValueError('invalid TotalHeaderSize=%d' % total_header_size)
        if len(buf) < total_header_size:
            buf.extend(fh.read(total_header_size - len(buf)))
        if len(buf) < total_header_size:
            raise ValueError('truncated header (< %d B)' % total_header_size)

    raw = bytes(buf)
    _pkg_name, p = _read_fstring(raw, p)
    p += 4  # PackageFlags
    name_count, name_off = struct.unpack_from('<ii', raw, p)
    p += 8
    if fv5 >= 1008:
        p += 8  # SoftObjectPathsCount + SoftObjectPathsOffset
    _loc_id, p = _read_fstring(raw, p)
    p += 8  # GatherableTextDataCount + GatherableTextDataOffset
    exp_count, exp_off = struct.unpack_from('<ii', raw, p)
    p += 8
    imp_count, imp_off, dep_off = struct.unpack_from('<iii', raw, p)

    if name_count < 0 or exp_count < 0 or imp_count < 0:
        raise ValueError('negative table count in summary')

    names = []
    np = name_off
    for _ in range(name_count):
        s, np = _read_fstring(raw, np)
        if np + 4 > len(raw):
            raise ValueError('truncated NameMap hash')
        np += 4
        names.append(s)

    imports = []
    for i in range(imp_count):
        base = imp_off + i * 40
        if base + 24 > len(raw):
            raise ValueError('truncated ImportMap entry')
        (obj_idx,) = struct.unpack_from('<I', raw, base + 20)
        imports.append(names[obj_idx] if obj_idx < len(names) else '')

    if exp_count > 0 and dep_off > exp_off:
        exp_stride = (dep_off - exp_off) // exp_count
    else:
        exp_stride = 112 if fv5 >= 1012 else 96
    if exp_stride < 48:
        raise ValueError('invalid ExportMap stride %d' % exp_stride)

    best_class = ''
    best_prio = 0
    for i in range(exp_count):
        base = exp_off + i * exp_stride
        if base + 4 > len(raw):
            raise ValueError('truncated ExportMap entry')
        (cls_idx,) = struct.unpack_from('<i', raw, base)
        if cls_idx < 0:
            idx = -cls_idx - 1
            resolved = imports[idx] if idx < len(imports) else 'Import'
        elif cls_idx > 0:
            resolved = 'Subobject'
        else:
            resolved = 'Package'
        if resolved in LOW_PRIORITY_CLASSES or resolved.startswith('MaterialExpression'):
            prio = 1
        else:
            prio = CLASS_PRIORITY.get(resolved, 10)
        if prio > best_prio or not best_class:
            best_prio = prio
            best_class = resolved

    if not best_class:
        best_class = 'UAsset'

    highlights = []
    seen_hl = set()
    foreign_mods = []
    seen_mods = set()
    self_low = self_mod.lower()

    for name in names:
        if name.startswith(('MPC_', 'M_', 'MI_', 'NS_', 'DT_')) and len(highlights) < 8 and name not in seen_hl:
            seen_hl.add(name)
            highlights.append(name)
        if name.startswith('/') and '/' in name[1:]:
            root = name[1:].split('/', 1)[0]
            if root and root not in BUILTIN_ROOTS and root.lower() != self_low and root not in seen_mods:
                if all(c.isalnum() or c == '_' for c in root):
                    seen_mods.add(root)
                    foreign_mods.append(root)

    return {
        'class': best_class,
        'fv5': fv5,
        'exports': exp_count,
        'imports': imp_count,
        'names': name_count,
        'highlights': highlights,
        'foreign_roots': foreign_mods,
    }


def _classify_ext(filename):
    low = filename.lower()
    if low.endswith('.uasset'):
        return 'UAsset'
    if low.endswith('.cfg'):
        return 'Cfg'
    if '.cfg_patch' in low:
        return 'CfgPatch'
    return None


def scan_folder(target, filter_str='', limit=50, cross_mod=''):
    """Walk target folder and summarize .uasset headers and .cfg / .cfg_patch* files."""
    target = os.path.abspath(target)
    if not os.path.isdir(target):
        raise SystemExit('no such directory: %s' % target)
    filt = filter_str.lower()
    entries = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            kind = _classify_ext(fn)
            if not kind:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, target).replace('\\', '/')
            if filt and filt not in rel.lower():
                continue
            item = {'rel': rel, 'kind': kind, 'bytes': os.path.getsize(full)}
            if kind == 'UAsset':
                try:
                    info = inspect_uasset_header(full, self_mod=cross_mod)
                    item.update(info)
                except Exception as e:
                    item['class'] = 'ERR'
                    item['error'] = str(e)
            entries.append(item)
            if limit and len(entries) >= limit:
                return entries, True
    return entries, False


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir', nargs='?', default='.', help='directory to scan (default: current directory)')
    ap.add_argument('--filter', default='', help='case-insensitive substring filter on relative path')
    ap.add_argument('--limit', type=int, default=50, help='max items to inspect (default: 50, 0 = unlimited)')
    ap.add_argument('--cross-mod', default='', help='own mod root name to exclude when flagging foreign /Mod/ refs')
    ap.add_argument('--json', action='store_true', help='emit structured JSON output')
    args = ap.parse_args(argv)

    entries, truncated = scan_folder(args.dir, filter_str=args.filter, limit=args.limit, cross_mod=args.cross_mod)
    if args.json:
        print(json.dumps({'root': os.path.abspath(args.dir), 'truncated': truncated, 'items': entries}, indent=2))
        return 0

    print('scan: %s (%d item(s)%s)' % (os.path.abspath(args.dir), len(entries), ', limit reached' if truncated else ''))
    for item in entries:
        if item['kind'] == 'UAsset':
            cls = item.get('class', 'UAsset')
            if cls == 'ERR':
                print('  [ERR]  %-55s (%s)' % (item['rel'], item.get('error', 'parse error')))
                continue
            parts = ['fv5=%d' % item['fv5'], 'exp=%d' % item['exports']]
            if item.get('highlights'):
                parts.append('refs=%s' % ','.join(item['highlights'][:4]))
            if item.get('foreign_roots'):
                parts.append('foreign_roots=%s' % ','.join(item['foreign_roots']))
            print('  [%-24s] %-45s %s' % (cls, item['rel'], ' | '.join(parts)))
        else:
            print('  [%-24s] %-45s %d B' % (item['kind'], item['rel'], item['bytes']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
