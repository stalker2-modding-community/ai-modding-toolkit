"""Pre-cook validator for STALKER 2 Zone Kit mod plugins (GFP descriptor, Content hygiene, cross-mod refs).

Checks a mod folder (under <kit>/Stalker2/Mods/<mod> or an explicit directory path) before
running sdk_cook_mod.py or packing:
  - Mod name matches ^[A-Za-z0-9_]+$
  - <Mod>.uplugin parses cleanly, checks ExplicitlyLoaded and BuiltInInitialFeatureState
  - Content/ warns on unrecognized extensions while failing on nested Content/Content/ or
    working directories (.git, __pycache__, node_modules, .ai)
  - Offline cross-mod hard reference check via uasset_scan.py against .uplugin Plugins declarations
  - Warns on Windows if Stalker2ModEditor is open (cache locks block sdk_cook_mod.py)

    python sdk_validate_mod.py <mod_name_or_dir> [--json]
    python sdk_validate_mod.py --all [--json]

Optionally provides audit_selected_in_editor() when imported inside the Unreal Editor Python runtime.
Pure stdlib. Exit code 0 on PASS/WARN, 1 on any FAIL.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2paths
import uasset_scan

NAME_RX = re.compile(r'^[A-Za-z0-9_]+$')
ALLOWED_CONTENT_EXTS = {'.uasset', '.uexp', '.ubulk', '.umap', '.cfg', '.wem', '.bnk'}
FORBIDDEN_CONTENT_DIRS = {'.git', '__pycache__', 'node_modules', '.ai'}
EDITORS = {'stalker2modeditor-win64-shipping.exe', 'stalker2modeditor-win64-shipping-cmd.exe'}


def running_editor_pids():
    """Return PIDs of running Zone Kit editor processes (Windows only)."""
    if os.name != 'nt':
        return []
    out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, errors='replace').stdout
    return [int(row[1]) for row in csv.reader(out.splitlines())
            if len(row) >= 2 and row[1].isdigit() and row[0].lower() in EDITORS]


def _allowed_content_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_CONTENT_EXTS or ext.startswith('.cfg_patch')


def validate_mod_dir(mod_dir):
    mod_dir = os.path.abspath(mod_dir)
    mod_name = os.path.basename(mod_dir)
    fails = []
    warns = []
    stats = {'mod': mod_name, 'dir': mod_dir, 'uassets': 0, 'cfgs': 0, 'declared_plugins': []}

    if not os.path.isdir(mod_dir):
        fails.append('mod directory does not exist: %s' % mod_dir)
        return {'mod': mod_name, 'fails': fails, 'warns': warns, 'stats': stats}

    if not NAME_RX.match(mod_name):
        fails.append('mod name %r must use only ASCII letters, digits and underscores' % mod_name)

    declared_plugins = set()
    uplugin = os.path.join(mod_dir, mod_name + '.uplugin')
    if not os.path.isfile(uplugin):
        fails.append('missing %s.uplugin descriptor' % mod_name)
    else:
        try:
            with open(uplugin, encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as e:
            fails.append('invalid JSON in %s: %s' % (os.path.basename(uplugin), e))
            data = None
        if isinstance(data, dict):
            if not data.get('ExplicitlyLoaded'):
                warns.append('%s.uplugin misses ExplicitlyLoaded: true' % mod_name)
            init_state = str(data.get('BuiltInInitialFeatureState') or '')
            if not init_state or init_state == 'None':
                warns.append('%s.uplugin misses BuiltInInitialFeatureState' % mod_name)
            for entry in data.get('Plugins') or []:
                if isinstance(entry, dict) and entry.get('Name'):
                    if entry.get('Enabled', True):
                        declared_plugins.add(str(entry['Name']).lower())
                        stats['declared_plugins'].append(str(entry['Name']))
                elif isinstance(entry, str):
                    declared_plugins.add(entry.lower())
                    stats['declared_plugins'].append(entry)

    content_dir = os.path.join(mod_dir, 'Content')
    if not os.path.isdir(content_dir):
        warns.append('missing Content/ directory')
    else:
        nested = os.path.join(content_dir, 'Content')
        if os.path.isdir(nested):
            fails.append('nested Content/Content/ directory detected (assets will fail mount lookup)')
        for dirpath, dirnames, filenames in os.walk(content_dir):
            bad_dirs = sorted(d for d in dirnames if d in FORBIDDEN_CONTENT_DIRS)
            for bd in bad_dirs:
                rel = os.path.relpath(os.path.join(dirpath, bd), mod_dir).replace('\\', '/')
                fails.append('forbidden working directory inside Content/: %s' % rel)
                dirnames.remove(bd)
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, mod_dir).replace('\\', '/')
                if not _allowed_content_file(fn):
                    warns.append('unrecognized file type inside Content/: %s' % rel)
                    continue
                low = fn.lower()
                if low.endswith('.uasset'):
                    stats['uassets'] += 1
                    try:
                        hdr = uasset_scan.inspect_uasset_header(full, self_mod=mod_name)
                        undeclared = [r for r in hdr.get('foreign_roots', []) if r.lower() not in declared_plugins]
                        if undeclared:
                            warns.append('%s references foreign root(s) %s not declared in %s.uplugin Plugins '
                                         '(cross-mod refs cook to NONE unless declared)'
                                         % (rel, ', '.join(undeclared), mod_name))
                    except Exception as e:
                        warns.append('%s header scan warning: %s' % (rel, e))
                elif low.endswith('.cfg') or '.cfg_patch' in os.path.splitext(low)[1]:
                    stats['cfgs'] += 1

    return {'mod': mod_name, 'dir': mod_dir, 'fails': fails, 'warns': warns, 'stats': stats}


def resolve_targets(args):
    if args.all:
        kit = s2paths.kit_dir()
        mods_root = os.path.join(kit, 'Stalker2', 'Mods')
        if not os.path.isdir(mods_root):
            raise SystemExit('Mods folder not found at %s' % mods_root)
        return [
            os.path.join(mods_root, d) for d in sorted(os.listdir(mods_root))
            if not d.startswith('.') and os.path.isdir(os.path.join(mods_root, d))
        ]
    target = args.target
    if os.path.isdir(target):
        return [os.path.abspath(target)]
    kit = s2paths.kit_dir()
    return [os.path.join(kit, 'Stalker2', 'Mods', target)]


def audit_selected_in_editor():
    """Run an AssetRegistry hard-dependency audit on currently selected assets inside Unreal Editor."""
    import unreal  # only available inside Unreal Editor Python

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    selected = unreal.EditorUtilityLibrary.get_selected_assets()
    if not selected:
        return {'status': 'ok', 'selected': 0, 'warnings': ['No assets selected in Content Browser.']}

    opts = unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=False,
        include_hard_package_references=True,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False,
    )
    results = []
    warnings = []
    for asset in selected:
        outer = asset.get_outer()
        pkg = outer.get_name() if outer else ''
        if not pkg:
            continue
        parts = pkg.strip('/').split('/')
        src_mod = parts[0] if parts else ''
        deps = [str(d) for d in (registry.get_dependencies(pkg, opts) or [])]
        foreign = []
        for dep in deps:
            root = dep.strip('/').split('/')[0] if dep.strip('/') else ''
            if root and root != src_mod and root not in uasset_scan.BUILTIN_ROOTS:
                foreign.append(dep)
        if foreign:
            warnings.append('%s has %d cross-mod hard dependency(s): %s' % (pkg, len(foreign), ', '.join(foreign)))
        results.append({'package': pkg, 'foreign_deps': foreign})
    return {'status': 'ok', 'selected': len(results), 'results': results, 'warnings': warnings}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('target', nargs='?', help='mod name under <kit>/Stalker2/Mods/ or path to a mod folder')
    ap.add_argument('--all', action='store_true', help='validate every mod under <kit>/Stalker2/Mods/')
    ap.add_argument('--json', action='store_true', help='emit structured JSON output')
    args = ap.parse_args(argv)

    if not args.all and not args.target:
        print(__doc__)
        return 2

    targets = resolve_targets(args)
    pids = running_editor_pids()
    reports = [validate_mod_dir(t) for t in targets]
    total_fails = sum(len(r['fails']) for r in reports)
    total_warns = sum(len(r['warns']) for r in reports)

    if args.json:
        print(json.dumps({
            'running_editor_pids': pids,
            'total_fails': total_fails,
            'total_warns': total_warns,
            'reports': reports,
        }, indent=2))
        return 1 if total_fails else 0

    if pids:
        print('WARN Stalker2ModEditor is running (pid %s): close it before running sdk_cook_mod.py'
              % ', '.join(map(str, pids)))
    for rep in reports:
        st = rep['stats']
        verdict = 'FAIL' if rep['fails'] else ('WARN' if rep['warns'] else 'PASS')
        print('[%s] %s (uassets=%d, cfgs=%d)' % (verdict, rep['mod'], st['uassets'], st['cfgs']))
        for msg in rep['fails']:
            print('  FAIL %s' % msg)
        for msg in rep['warns']:
            print('  WARN %s' % msg)
    print('sdk_validate_mod: %d mod(s), %d FAIL, %d WARN' % (len(reports), total_fails, total_warns))
    return 1 if total_fails else 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except s2paths.S2PathError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
