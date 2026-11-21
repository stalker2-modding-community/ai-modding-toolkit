r"""Cook a Zone Kit override mod and pack it into a .pak/.utoc/.ucas trio with retoc.

Why this exists instead of the kit's own bats (details in the stalker2-zonekit skill):
  - PakPlainMod.bat hardcodes -skipcook: on a never-cooked mod it says BUILD SUCCESSFUL and writes an EMPTY pak.
  - it also passes -skipiostore: a legacy pak cannot override a cooked asset.
  - Windows Smart App Control can block kit binaries (UAT's EpicGames.Perforce.dll, UnrealPak's UnrealPak-Json.dll). This
    script runs the cook commandlet directly and packs with `retoc to-zen --version UE5_5` from SavedMods/Cooked, so it
    works either way; there is no need to change Smart App Control.
  - retoc writes no /Game package redirect, so the script always adds it (zen_add_redirect.py); without it the override
    mounts but never loads.

Authoring happens first: in the editor GUI (pick the mod in the startup selector, edit the /<mod>/ copy, save, accept
Check Out Assets) or, for assets already in the mod, with headless editor Python. This script only cooks and packs what is
in <kit>/Stalker2/Mods/<mod>. It stops, before packing, when the cook log reports a material that failed to compile (the
game would draw the default grid material) or a Niagara script error (the system would draw nothing).

    python sdk_cook_mod.py <mod> [--pack-cfg]                     cook + pack, output in the work folder
    python sdk_cook_mod.py <mod> --install "<folder in ~mods>" [--name <base>] [--priority <N>] [--pack-cfg]
    python sdk_cook_mod.py <mod> --pack-only --out <dir> [--name <base>] [--priority <N>] [--pack-cfg]  pack existing cook
    add --clean-cooked (not with --pack-only) to delete <kit>/Stalker2/SavedMods/Cooked/<mod> before cooking

--install takes a folder name inside the game's ~mods (created if missing); it must stay inside ~mods. --name defaults to
the mod name. Mod and --name use only letters, digits and underscores. --priority adds the _<N>_P tail; leave it off unless
the mod needs one (decide per mod, see the stalker2-paks skill). --pack-cfg opts in to packing <mod>/Content/*.cfg* into a
companion <base>_Cfg[_<N>_P].pak via repak (or deleting a stale one if no cfgs remain; plain paks with @BaseGame/ refurls
warn because they are untested in game). The cook never clears its old output, so an asset you removed from the mod is
packed again: use --clean-cooked after removing assets. About two and a half minutes for a cook.
Needs the Zone Kit and retoc (see s2paths.py) and the cityhash module (pip install cityhash); --pack-cfg also needs repak.
"""
import os, re, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2paths

NAME_RX = re.compile(r'^[A-Za-z0-9_]+$')


def kit_paths():
    kit = s2paths.kit_dir()
    return {'kit': kit,
            'uproject': os.path.join(kit, 'Stalker2', 'Stalker2.uproject'),
            'editor_cmd': os.path.join(kit, 'Stalker2', 'Binaries', 'Win64', 'Stalker2ModEditor-Win64-Shipping-Cmd.exe'),
            'cooked': os.path.join(kit, 'Stalker2', 'SavedMods', 'Cooked')}


def cook(mod):
    """Run the override cook commandlet directly, with the arguments UAT passes it, so neither UAT nor UnrealPak is needed.
    Returns True on a good cook."""
    k = kit_paths()
    plugin = os.path.join(k['kit'], 'Stalker2', 'Mods', mod, mod + '.uplugin')
    if not os.path.isfile(plugin):
        raise SystemExit('no such mod plugin: %s\ncreate it with: "%s" %s' % (plugin, os.path.join(k['kit'], 'CreatePlainMod.bat'), mod))
    if not os.path.isfile(k['editor_cmd']):
        raise SystemExit('the kit editor command line exe is missing: %s' % k['editor_cmd'])
    log_path = os.path.join(s2paths.work_dir(), 'cook_%s.log' % mod)
    cmd = [k['editor_cmd'], k['uproject'], '-run=Cook', '-CookDir=' + plugin, '-TargetPlatform=Windows',
           '-ddc=ModEditorInstalledDerivedDataBackendGraph', '-unversioned',
           '-outputdir=' + os.path.join(k['cooked'], mod, 'Windows', 'OverrideContent', 'Windows'), '-IgnoreMissingReferences',
           '-SkipSaveAssetRegistry', '-modcookoverridecontent', '-nowrite', '-CookAgainstFixedBase',
           '-CustomConfig=ModCookOverrideContent', '-OverrideShaderLibraryName=%s_OverrideContent' % mod, '-fileopenlog',
           '-manifests', '-dlcname=' + mod, '-basedonreleaseversion=Latest', '-abslog=' + log_path, '-stdout', '-unattended',
           '-NoLogTimes']
    print('cooking %s (a couple of minutes) ...' % mod, flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace', cwd=k['kit'])
    log = r.stdout + r.stderr
    for line in log.splitlines():
        if any(x in line for x in ('Packages Cooked', 'Missing cached shadermap')):
            print('  ' + line.strip()[:200])
    # A material that fails to compile still cooks and packs, but ships with no shader map: the game draws the default grid
    # material in its place. Stop the build instead.
    failed = [l.strip() for l in log.splitlines() if 'Failed to compile Material' in l or 'Default Material will be used' in l]
    if failed:
        raise SystemExit('material compile error, the build would render as the default grid material (log: %s):\n  %s'
                         % (log_path, '\n  '.join(l[:200] for l in failed[:5])))
    # A Niagara system whose scripts fail (for example modules the kit does not ship) also cooks without a cook failure and
    # draws nothing in game. Stop on Niagara script errors.
    nerr = [l.strip() for l in log.splitlines() if ('LogNiagara' in l and 'Error' in l) or 'Unknown Function Call' in l
            or ('Niagara' in l and 'failed to compile' in l.lower())]
    if nerr:
        raise SystemExit('Niagara compile error, the system would be dead in game (log: %s):\n  %s'
                         % (log_path, '\n  '.join(l[:200] for l in nerr[:8])))
    if r.returncode != 0 or 'Packages Cooked' not in log:
        raise SystemExit('cook failed (exit %s), see %s' % (r.returncode, log_path))
    if 'Missing cached shadermap' not in log:
        print('  NOTE: no material recompiled. If you byte-patched a material constant, the OLD shaders were cooked: renew the\n'
              '  material StateId first (sdk_renew_state_id.py). An editor save renews it on its own.')
    return True


def pack(mod, name, out_dir):
    """Lay the cooked override content out as Stalker2/Content/... and convert it to a trio with retoc, then add the /Game
    redirect while copying the trio into out_dir. Only overridden assets and the shader archive go in; the plugin's own
    bookkeeping assets are not needed for an override."""
    content = os.path.join(kit_paths()['cooked'], mod, 'Windows', 'OverrideContent', 'Windows', 'Stalker2', 'Mods', mod, 'Content')
    if not os.path.isdir(content):
        raise SystemExit('no cooked output for %s at %s (cook first)' % (mod, content))
    retoc = s2paths.tool('retoc')
    from zen_add_redirect import add_redirect, _cityhash
    _cityhash()                                   # fail before any work when cityhash is missing
    work = os.path.join(s2paths.work_dir(), 'zen_' + mod)
    shutil.rmtree(work, ignore_errors=True)
    try:
        dest_root = os.path.join(work, 'in', 'Stalker2', 'Content')
        for root, _, files in os.walk(content):
            rel = os.path.relpath(root, content)
            for f in files:
                shader = f.startswith('ShaderArchive-') and f.endswith('.ushaderbytecode')
                asset = f.endswith(('.uasset', '.uexp', '.ubulk')) and rel != '.' and not f.startswith('__ModKit')
                if not (shader or asset):
                    continue
                d = os.path.join(dest_root, rel) if asset else dest_root
                os.makedirs(d, exist_ok=True)
                shutil.copyfile(os.path.join(root, f), os.path.join(d, f))
        trio = os.path.join(work, 'trio')
        os.makedirs(trio)
        r = subprocess.run([retoc, 'to-zen', '--version', 'UE5_5', os.path.join(work, 'in'), os.path.join(trio, name + '.utoc')],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit('retoc to-zen failed: ' + r.stdout + r.stderr)
        for ext in ('.pak', '.utoc', '.ucas'):
            if not os.path.isfile(os.path.join(trio, name + ext)):
                raise SystemExit('retoc produced no ' + name + ext)
        os.makedirs(out_dir, exist_ok=True)
        for ext in ('.pak', '.utoc', '.ucas'):
            try:
                os.remove(os.path.join(out_dir, name + ext))
            except FileNotFoundError:
                pass
        archives = [os.path.join(content, f) for f in os.listdir(content) if f.startswith('ShaderArchive-') and f.endswith('.ushaderbytecode')]
        add_redirect(os.path.join(trio, name + '.utoc'), out_dir, archives[0] if len(archives) == 1 else None)
        # The game reads each compressed block rounded up to 16 bytes. If the last block ends the file short of that, the
        # container fails to mount (log: Failed to mount IoStore container) and the game silently uses its own assets.
        with open(os.path.join(out_dir, name + '.ucas'), 'ab') as pad:
            pad.write(b'\0' * 16)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out = [os.path.join(out_dir, name + ext) for ext in ('.pak', '.utoc', '.ucas')]
    for f in out:
        if not os.path.isfile(f):
            raise SystemExit('no %s in %s after packing' % (os.path.basename(f), out_dir))
        print('  out:', f, '(%d bytes)' % os.path.getsize(f))
    return out


def clean_cooked(mod):
    """Delete <kit>/Stalker2/SavedMods/Cooked/<mod> and nothing else."""
    if not NAME_RX.match(mod):
        raise SystemExit('mod %r: use only letters, digits and underscores' % mod)
    k = kit_paths()
    if not os.path.isfile(os.path.join(k['kit'], 'Stalker2', 'Mods', mod, mod + '.uplugin')):
        raise SystemExit('no mod named %s in %s, nothing cleaned' % (mod, os.path.join(k['kit'], 'Stalker2', 'Mods')))
    cooked = os.path.realpath(k['cooked'])
    target = os.path.realpath(os.path.join(cooked, mod))
    if os.path.normcase(os.path.dirname(target)) != os.path.normcase(cooked) or os.path.basename(target) != mod or \
            [p.lower() for p in cooked.replace('\\', '/').split('/')[-3:]] != ['stalker2', 'savedmods', 'cooked']:
        raise SystemExit('refusing to delete %s: not <kit>/Stalker2/SavedMods/Cooked/%s' % (target, mod))
    if os.path.isdir(target):
        shutil.rmtree(target)
        print('removed the old cook output %s' % target)
    else:
        print('no old cook output at %s' % target)


def install_dir(folder):
    """<mods>/<folder>, refusing anything that would land outside ~mods."""
    mods = os.path.realpath(s2paths.mods_dir())
    if not os.path.isdir(mods):
        raise SystemExit('no ~mods folder at %s (create it, or fix the mods path in s2paths.py)' % mods)
    target = os.path.realpath(os.path.join(mods, folder))
    try:
        inside = os.path.normcase(os.path.commonpath([mods, target])) == os.path.normcase(mods)
    except ValueError:                            # another drive
        inside = False
    if not inside:
        raise SystemExit('--install must name a folder inside ~mods (%s), not %s' % (mods, folder))
    return target


def _cfg_pak_name(base, priority):
    return '%s_Cfg_%s_P.pak' % (base, priority) if priority else '%s_Cfg.pak' % base


def pack_cfg(mod, base, priority, out_dir, repak=None):
    """Pack any .cfg or .cfg_patch* files under Content/ into a companion _Cfg[_<N>_P].pak via repak."""
    out_pak = os.path.join(out_dir, _cfg_pak_name(base, priority))
    content = os.path.join(kit_paths()['kit'], 'Stalker2', 'Mods', mod, 'Content')
    cfgs = []
    if os.path.isdir(content):
        for root, dirs, files in os.walk(content):
            dirs.sort()
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext == '.cfg' or ext.startswith('.cfg_patch'):
                    cfgs.append(os.path.join(root, f))
    if not cfgs:
        if os.path.isfile(out_pak):
            os.remove(out_pak)
            print('  removed stale cfg pak: %s (no cfg files in Content/)' % out_pak)
        return None
    if repak is None:
        repak = s2paths.tool('repak')
    work = os.path.join(s2paths.work_dir(), 'cfg_' + mod)
    shutil.rmtree(work, ignore_errors=True)
    try:
        for src in cfgs:
            rel = os.path.relpath(src, content)
            rel_posix = rel.replace('\\', '/')
            dst = os.path.join(work, 'Stalker2', 'Content', rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            print('  cfg: Stalker2/Content/%s' % rel_posix)
            with open(src, encoding='utf-8', errors='replace') as fh:
                if '@BaseGame/' in fh.read():
                    print('  WARN: %s contains @BaseGame/ refurl (plain paks may need relative refurls; verify in game)' % rel_posix)
        os.makedirs(out_dir, exist_ok=True)
        if os.path.exists(out_pak):
            os.remove(out_pak)
        r = subprocess.run([repak, 'pack', '--version', 'V11', work, out_pak], capture_output=True, text=True)
        if r.returncode or not os.path.isfile(out_pak):
            raise SystemExit('repak pack failed for cfg companion pak: ' + (r.stdout + r.stderr).strip())
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print('  out: %s (%d bytes, %d cfg file(s))' % (out_pak, os.path.getsize(out_pak), len(cfgs)))
    return out_pak


def arg(args, flag, default=None):
    if flag not in args:
        return default
    i = args.index(flag)
    if i + 1 >= len(args) or args[i + 1].startswith('--'):
        raise SystemExit('%s needs a value' % flag)
    return args[i + 1]


def main():
    args = sys.argv[1:]
    if not args or '-h' in args or '--help' in args or args[0].startswith('-'):
        print(__doc__)
        return 0 if ('-h' in args or '--help' in args) else 2
    mod = args[0]
    priority = arg(args, '--priority')
    base = arg(args, '--name', mod)
    for what, v in (('mod', mod), ('--name', base)):
        if not NAME_RX.match(v):
            raise SystemExit('%s %r: use only letters, digits and underscores' % (what, v))
    if priority is not None and not priority.isdigit():
        raise SystemExit('--priority must be a whole number, got %r' % priority)
    name = base + ('_%s_P' % priority if priority else '')
    want_cfg = '--pack-cfg' in args
    if '--pack-only' in args:
        if '--clean-cooked' in args:
            raise SystemExit('--clean-cooked deletes the cook that --pack-only would pack: use one or the other')
        out_dir = arg(args, '--out')
        if not out_dir:
            raise SystemExit('--pack-only needs --out <dir>')
        repak = s2paths.tool('repak') if want_cfg else None
        pack(mod, name, out_dir)
    else:
        folder = arg(args, '--install')
        out_dir = install_dir(folder) if folder else os.path.join(s2paths.work_dir(), 'out_' + mod)
        repak = s2paths.tool('repak') if want_cfg else None
        if '--clean-cooked' in args:
            clean_cooked(mod)
        cook(mod)
        pack(mod, name, out_dir)
    if want_cfg:
        pack_cfg(mod, base, priority, out_dir, repak=repak)
    else:
        stale_cfg = os.path.join(out_dir, _cfg_pak_name(base, priority))
        if os.path.isfile(stale_cfg):
            print('  NOTE: existing %s in %s was left untouched (pass --pack-cfg to update/remove it)'
                  % (os.path.basename(stale_cfg), out_dir))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except s2paths.S2PathError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
