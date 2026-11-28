"""S2MM toolkit: make (or update) your mod's S2MM settings from s2mm_settings.json.

Run it INSIDE the Zone Kit with your mod open: File > Execute Python Script > pick this file.
(It also runs headless: Stalker2ModEditor.exe <uproject> -run=pythonscript -script=<this file>.)

What it does, in your mod (it never touches S2MM or any game file):
  1. checks s2mm_settings.json (next to this script, or the file named in the S2MM_SETTINGS environment variable)
  2. /<YourMod>/S2MM/BP_<YourMod>_S2MM: your settings actor (a copy of S2MM's own, so it already implements BPI_S2MM_Provider),
     with one variable per setting, named like the setting id, holding its default
  3. /<YourMod>/S2MM/BP_<YourMod>_S2MMSubsystem: the starter that keeps that actor alive
  4. adds S2MM as a dependency in your mod's .uplugin (S2MM is never packed into your mod)
  5. writes out/<YourMod>/: two pastes, a copy window (copy_window.ps1) and SESSION_GUIDE.md with the few clicks left
Run it again after you change the settings file: new variables are added, the pastes are rewritten.
Report: out/<YourMod>/s2mm_make_report.txt (last line ALL DONE or FAILED).
MIT licence, part of S2MM (Stalker 2 Mod Menu)."""
import os, re, sys, json, traceback
import unreal

try:
    ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:      # the kit normally sets __file__; if not, say where the toolkit is with the S2MM_TOOLKIT environment variable
    ROOT = os.environ.get('S2MM_TOOLKIT', os.getcwd())
sys.path.insert(0, os.path.join(ROOT, 'lib'))
import importlib
import bpgen, s2help, s2mm_settings
for m in (bpgen, s2help, s2mm_settings):
    importlib.reload(m)                    # the kit keeps modules loaded between runs
from s2mm_settings import load, names, provider_graph, subsystem_graph, value_settings, TYPES, SettingsError

L = unreal.BlueprintEditorLibrary
EAL = unreal.EditorAssetLibrary
lines = []
OUT = [None]


def say(*a):
    s = ' '.join(str(x) for x in a)
    lines.append(s)
    unreal.log('[S2MM make] ' + s)


def existing_vars(bp, tmp):
    t = unreal.AssetExportTask()
    t.object, t.filename, t.automated, t.prompt, t.replace_identical, t.exporter = bp, tmp, True, False, True, None
    unreal.Exporter.run_asset_export_task(t)
    txt = open(tmp, encoding='utf-8', errors='replace').read() if os.path.isfile(tmp) else ''
    if os.path.isfile(tmp):
        os.remove(tmp)
    return set(re.findall(r'VarName="([^"]+)"', txt)), bool(txt)


def add_var(bp, name, ty, tmp):
    """add_member_variable does not refuse an existing name (it makes Name_0): check the real list first"""
    have, ok = existing_vars(bp, tmp)
    if not ok:
        raise RuntimeError('cannot read the variables of ' + bp.get_name())
    if name in have:
        return 'exists'
    L.add_member_variable(bp, name, ty)
    return 'added'


def var_type(kind):
    return {'bool': L.get_basic_type_by_name('bool'), 'int': L.get_basic_type_by_name('int'), 'real': L.get_basic_type_by_name('real'),
            'string': L.get_basic_type_by_name('string'), 'vector': L.get_struct_type(unreal.Vector.static_struct())}[kind]


def default_value(s):
    kind = TYPES[s['type']][0]
    if kind == 'bool':
        return bool(s['default'])
    if kind == 'int':
        return int(s['default'])
    if kind == 'real':
        return float(s['default'])
    if kind == 'string':
        return str(s['default'])
    return unreal.Vector(*[float(v) for v in s['default']])


COPY_WINDOW = r'''# S2MM: always-on-top window, one Copy button per paste. Copy retries while the clipboard is busy, reads the clipboard back
# and compares it with the file: green "Copied - checked" only when it really holds this paste.
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$items = @(
    @("1  Settings actor   __PROV__ > Event Graph", "paste_provider.txt", "S2MM (made by s2mm_make.py): when S2MM asks"),
    @("2  Starter          __SUB__ > Event Graph", "paste_subsystem.txt", "S2MM (made by s2mm_make.py): start ticking")
)
$form = New-Object Windows.Forms.Form
$form.Text = "S2MM - __MOD__ pastes"
$form.TopMost = $true
$form.Font = New-Object Drawing.Font("Segoe UI", 10)
$form.AutoSize = $true; $form.AutoSizeMode = "GrowAndShrink"; $form.Padding = New-Object Windows.Forms.Padding(10)
$flow = New-Object Windows.Forms.FlowLayoutPanel
$flow.FlowDirection = "TopDown"; $flow.AutoSize = $true; $flow.WrapContents = $false
$form.Controls.Add($flow)
$help = New-Object Windows.Forms.Label
$help.AutoSize = $true; $help.MaximumSize = New-Object Drawing.Size(560, 0)
$help.Text = "Click Copy and wait for green 'Copied - checked'. Red means the clipboard was busy: click again. After Ctrl+V, look for the comment named on the right."
$flow.Controls.Add($help)
function Copy-Checked($path) {
    $text = [IO.File]::ReadAllText($path)
    for ($i = 0; $i -lt 20; $i++) {
        try {
            [Windows.Forms.Clipboard]::Clear()
            $data = New-Object Windows.Forms.DataObject
            $data.SetData([Windows.Forms.DataFormats]::UnicodeText, $text)
            [Windows.Forms.Clipboard]::SetDataObject($data, $true, 10, 100)
            if ([Windows.Forms.Clipboard]::GetText() -eq $text) { return "ok" }
        } catch { }
        Start-Sleep -Milliseconds 150
    }
    return "busy"
}
foreach ($it in $items) {
    $line = New-Object Windows.Forms.FlowLayoutPanel
    $line.AutoSize = $true; $line.WrapContents = $false
    $b = New-Object Windows.Forms.Button
    $b.Text = "Copy"; $b.Width = 150; $b.Height = 28
    $b.Tag = Join-Path $Dir $it[1]
    $b.Add_Click({ param($s, $e)
        $s.Text = "copying..."; $s.BackColor = [Drawing.Color]::LightYellow; $s.Refresh()
        if ((Copy-Checked $s.Tag) -eq "ok") { $s.Text = "Copied - checked"; $s.BackColor = [Drawing.Color]::LightGreen }
        else { $s.Text = "FAILED - click again"; $s.BackColor = [Drawing.Color]::LightCoral } })
    $l = New-Object Windows.Forms.Label
    $l.AutoSize = $true; $l.Padding = New-Object Windows.Forms.Padding(0, 5, 0, 0)
    $l.Font = New-Object Drawing.Font("Consolas", 10)
    $l.Text = $it[0] + "     (look for: " + $it[2] + ")"
    if (-not (Test-Path $b.Tag)) { $b.Enabled = $false; $l.Text += "  (file missing)" }
    $line.Controls.Add($b); $line.Controls.Add($l)
    $flow.Controls.Add($line)
}
[void]$form.ShowDialog()
'''

GUIDE = '''# S2MM settings for __MOD__: the clicks left (made by s2mm_make.py)

s2mm_make.py already made your settings actor (__PROV_NAME__), its starter (__SUB_NAME__), one variable per setting, and added
S2MM as a dependency of your mod. Two pastes are left. Open the copy window first: right-click `copy_window.ps1` in this folder >
**Run with PowerShell**. It stays on top of the kit.

Every paste: wait for green **"Copied - checked"** before Ctrl+V, and check the "look for" comment after it.

## Step 1: open
1. Start the kit and pick **__MOD__** in the mod dropdown.
2. Ctrl+P, type `BP_S2MM_Manager`, press Enter. This loads S2MM so the pastes find its parts. Leave it open; don't change it.

## Step 2: Copy 1, your settings actor
1. Ctrl+P, open `__PROV_NAME__`, then its **Event Graph**.
2. Clear first: **YES**. Click an empty spot, Ctrl+A, Delete.
3. Click **Copy 1**, wait for green, Ctrl+V.
4. Look for: a comment box starting **"S2MM (made by s2mm_make.py): when S2MM asks"**.
5. Compile: **YES**. Save: **YES**.

## Step 3: Copy 2, the starter
1. Ctrl+P, open `__SUB_NAME__`, then its **Event Graph**.
2. Clear first: **YES** (it may be empty already).
3. Click **Copy 2**, wait for green, Ctrl+V.
4. Look for: a comment box starting **"S2MM (made by s2mm_make.py): start ticking"**.
5. Compile: **YES**. Save: **YES**.

## Step 4: package
1. File > Save All.
2. With **__MOD__** picked, press **Package**.
3. Players need S2MM installed too. Your settings show in game under Esc > MODS > S2MM tab > **__NAME__**.

## Reading your settings in your own Blueprints
Your values live in variables on `__PROV_NAME__`, named like the setting ids:
__VARS__
- Anywhere: **Get Actor Of Class** (__PROV_NAME__) > **Cast** > read the variable.
- Or ask S2MM at any time: get the S2MM manager (**Get Actor Of Class** BP_S2MM_Manager), call **S2MM_Get** (ModID `__ID__`,
  SettingID), then read **ResultBool / ResultInt / ResultFloat / Result** on the manager.
'''


def main():
    sp = os.environ.get('S2MM_SETTINGS') or os.path.join(ROOT, 's2mm_settings.json')
    say('settings file:', sp)
    cfg = load(sp)
    nm = names(cfg)
    mod = cfg['mod']
    out = os.path.join(ROOT, 'out', mod)
    os.makedirs(out, exist_ok=True)
    OUT[0] = out
    tmp = os.path.join(out, '_vars.t3d')
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    reg.scan_paths_synchronous(['/S2MM/', '/%s/' % mod], True)
    if not EAL.does_asset_exist('/S2MM/Core/BP_S2MM_Manager') or not EAL.does_asset_exist('/S2MM/Core/BP_S2MM_Self'):
        raise RuntimeError('S2MM is not in this kit: copy the S2MM kit package into Stalker2/Mods/S2MM first (see README)')
    proj = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    upl = os.path.join(proj, 'Mods', mod, mod + '.uplugin')
    if not os.path.isfile(upl):
        raise RuntimeError('no kit mod named "%s" (looked for %s). "mod" must be your mod folder name.' % (mod, upl))
    # 1. the settings actor
    if not EAL.does_asset_exist(nm['provider']):
        ok = EAL.duplicate_asset('/S2MM/Core/BP_S2MM_Self', nm['provider'])
        say('settings actor made:', nm['provider'], bool(ok))
    else:
        say('settings actor exists:', nm['provider'])
    pb = unreal.load_asset(nm['provider'])
    for s in value_settings(cfg):
        say('  variable', s['id'], '(%s)' % TYPES[s['type']][0], add_var(pb, s['id'], var_type(TYPES[s['type']][0]), tmp))
    L.compile_blueprint(pb)
    cdo = unreal.get_default_object(pb.generated_class())
    for s in value_settings(cfg):
        try:
            cdo.set_editor_property(s['id'], default_value(s))
        except Exception as e:
            say('  default for', s['id'], 'not set:', str(e)[:120])
    L.compile_blueprint(pb)
    EAL.save_loaded_asset(pb, False)
    # 2. the starter
    if not EAL.does_asset_exist(nm['subsystem']):
        fac = unreal.BlueprintFactory()
        fac.set_editor_property('parent_class', unreal.ModWorldSubsystem)
        sb = unreal.AssetToolsHelpers.get_asset_tools().create_asset(nm['subsystem'].split('/')[-1], nm['folder'], unreal.Blueprint, fac)
        say('starter made:', nm['subsystem'], bool(sb))
    sb = unreal.load_asset(nm['subsystem'])
    say('  variable Provider', add_var(sb, 'Provider', L.get_object_reference_type(pb.generated_class()), tmp))
    L.compile_blueprint(sb)
    EAL.save_loaded_asset(sb, False)
    # 3. S2MM as a dependency of the mod
    d = json.load(open(upl, encoding='utf-8-sig'))
    deps = d.setdefault('Plugins', [])
    if not any(p.get('Name') == 'S2MM' for p in deps):
        deps.append({'Name': 'S2MM', 'Enabled': True})
        open(upl, 'w', encoding='utf-8', newline='\r\n').write(json.dumps(d, indent='\t') + '\n')
        say('S2MM added as a dependency in', upl)
    else:
        say('S2MM already a dependency')
    # 4. pastes, copy window, guide
    for fn, gfn in (('paste_provider.txt', provider_graph), ('paste_subsystem.txt', subsystem_graph)):
        g = gfn(cfg)
        open(os.path.join(out, fn), 'w', encoding='utf-8', newline='').write(g.text())
        say('wrote', fn, g.stats())
    pn, sn = nm['provider'].split('/')[-1], nm['subsystem'].split('/')[-1]
    open(os.path.join(out, 'copy_window.ps1'), 'w', encoding='utf-8').write(
        COPY_WINDOW.replace('__PROV__', pn).replace('__SUB__', sn).replace('__MOD__', mod))
    vars_txt = '\n'.join('- `%s` (%s): %s' % (s['id'], TYPES[s['type']][0], s['label']) for s in value_settings(cfg)) or '- (no value settings)'
    btns = [s for s in cfg['settings'] if s['type'] == 'button']
    if btns:
        vars_txt += ('\n\nButtons have no variable. In `%s`, under "S2MM_OnValue", each button has a Branch with a comment "Button ... was '
                     'pressed": put your nodes on its True pin. Buttons: %s' % (pn, ', '.join('`%s`' % b['id'] for b in btns)))
    open(os.path.join(out, 'SESSION_GUIDE.md'), 'w', encoding='utf-8').write(
        GUIDE.replace('__MOD__', mod).replace('__PROV_NAME__', pn).replace('__SUB_NAME__', sn).replace('__NAME__', cfg['name'])
             .replace('__ID__', cfg['id']).replace('__VARS__', vars_txt))
    say('next: open', os.path.join(out, 'SESSION_GUIDE.md'))
    say('ALL DONE')


try:
    main()
except SettingsError as e:
    say('FAILED: the settings file has problems:\n' + str(e))
except Exception:
    say('FAILED', traceback.format_exc())
rep = os.path.join(OUT[0] or ROOT, 's2mm_make_report.txt')
open(rep, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
unreal.log('[S2MM make] report: ' + rep)
