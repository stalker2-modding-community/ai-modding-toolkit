# Cooking and packing a Zone Kit mod

## Contents
- Order: the kit's own tools first, retoc as the fallback
- PakPlainMod.bat traps
- The kit's own cook (RunUAT)
- The fallback: the cook commandlet, retoc, zen_add_redirect
- The /Game package redirect
- Cook logs that prove (or disprove) a recompile
- Proving the cooked trio changed
- One mod, several paks
- Detached runs, locks and timing
- Smart App Control blocks
- Classifier lists and cook rules

## Order: the kit's own tools first, retoc as the fallback
1. The kit's own cook and packer. They write the /Game package redirect themselves.
2. If a kit binary is blocked or fails: `python scripts/sdk_cook_mod.py <mod>` (the cook commandlet run directly, then
   `retoc to-zen --version UE5_5`, then the redirect added by zen_add_redirect.py).
Either way: never cook while the kit editor is open, and prove the result in game with a loud value (SKILL.md).
Pak names, the `_<N>_P` priority suffix and ~mods layout: stalker2-paks.

## PakPlainMod.bat traps
The shipped `PakPlainMod.bat <mod>` calls `RunUAT.bat GSCCookModOverrideContent ... -skipcook -skipiostore`:
- `-skipcook`: on a never-cooked mod it prints BUILD SUCCESSFUL and writes an EMPTY pak ("Added 0 entries").
- `-skipiostore`: the result is a bare legacy .pak, which cannot override a cooked asset (the engine resolves packages through
  IoStore first). A working override is the .pak stub + .utoc + .ucas trio.
`CreatePlainMod.bat <name>` (RunUAT `GSCCreatePlainMod`) works as shipped.

## The kit's own cook (RunUAT)
- `"<kit>/Engine/Build/BatchFiles/RunUAT.bat" -List -nocompile -nocompileuat` lists the kit's commands: `GSCCookMod`,
  `GSCCookModOverrideContent`, `GSCCookModNewContent`, `GSCCreatePlainMod`.
- A real override cook is PakPlainMod's line WITHOUT `-skipcook` and `-skipiostore`, PLUS
  `-UnrealExe=<kit>/Stalker2/Binaries/Win64/Stalker2ModEditor-Win64-Shipping-Cmd.exe` (the kit ships no `UnrealEditor-Cmd.exe`,
  which UAT looks for by default):

      "<kit>/Engine/Build/BatchFiles/RunUAT.bat" GSCCookModOverrideContent "-Project=<kit>/Stalker2/Stalker2.uproject"
        "-PluginPath=<kit>/Stalker2/Mods/<mod>/<mod>.uplugin" -TargetPlatform=Win64 -CustomConfig=ModCookOverrideContent
        -UnrealExe=<kit>/Stalker2/Binaries/Win64/Stalker2ModEditor-Win64-Shipping-Cmd.exe -nocompile -nocompileuat

- The kit stages its output under `<kit>/Stalker2/SavedMods/Staged/<mod>/...`.
- UAT's log, with the exact "Running:" command lines it passed on, is under `%APPDATA%/Unreal Engine/AutomationTool/Logs/`
  (one folder per kit install, named after its path) as `Log.txt`.
- A kit cook carries its own shader archive and redirect: it cannot be merged into a trio built by other means. Ship it as its
  own trio.

## The fallback: the cook commandlet, retoc, zen_add_redirect
Run `python scripts/sdk_validate_mod.py <mod>` before cooking to catch bad `.uplugin` metadata, non-asset files in `Content/`, and foreign `/Mod/` imports early.
`python scripts/sdk_cook_mod.py <mod> [--install <folder under ~mods>] [--name <base>] [--priority <N>] [--pack-cfg]` cooks and
packs; `--pack-only --out <dir>` packs the existing cook again (for example into a release folder). `--name` defaults to the
mod name; `--priority` adds the `_<N>_P` tail only when given. Pass `--pack-cfg` to also pack `<mod>/Content` `.cfg` /
`.cfg_patch*` files via `repak pack --version V11` into `<base>_Cfg[_<N>_P].pak` (matching priority, printing packed files,
warning on `@BaseGame/` refurls since plain-pak loading with `@BaseGame/` is untested in game, and deleting a stale `_Cfg`
pak if all cfgs are later removed); without `--pack-cfg`, existing `_Cfg` paks are left alone. Mod names must match
`^[A-Za-z0-9_]+$`. Judge the run by its result (exit code, the files, the game), never by a grep of its output. The script
stops before packing when the cook log holds `Failed to compile Material` / `Default Material will be used`, or a Niagara
script error (a `LogNiagara` line with `Error`, `Unknown Function Call`, or a Niagara `failed to compile`).

What it runs, if you ever need it by hand:
1. The cook commandlet, directly (the arguments UAT passes, taken from its log):

       <kit>/Stalker2/Binaries/Win64/Stalker2ModEditor-Win64-Shipping-Cmd.exe <kit>/Stalker2/Stalker2.uproject -run=Cook
         -CookDir=<kit>/Stalker2/Mods/<mod>/<mod>.uplugin -TargetPlatform=Windows -ddc=ModEditorInstalledDerivedDataBackendGraph
         -unversioned -outputdir=<kit>/Stalker2/SavedMods/Cooked/<mod>/Windows/OverrideContent/Windows -IgnoreMissingReferences
         -SkipSaveAssetRegistry -modcookoverridecontent -nowrite -CookAgainstFixedBase -CustomConfig=ModCookOverrideContent
         -OverrideShaderLibraryName=<mod>_OverrideContent -fileopenlog -manifests -dlcname=<mod> -basedonreleaseversion=Latest
         -abslog=<log> -stdout -unattended -NoLogTimes

   About 2.5 minutes for a small material, shaders included.
2. Lay the cooked content (`.../OverrideContent/Windows/Stalker2/Mods/<mod>/Content/`) out as `Stalker2/Content/<path>`: assets
   in their folders, the `ShaderArchive-*.ushaderbytecode` at the Content root, `__ModKit*` bookkeeping files left out.
3. `retoc to-zen --version UE5_5 <that folder> <out>/<name>.utoc`. Always `UE5_5`: another version writes a container header
   the game rejects (stalker2-paks).
4. `python scripts/zen_add_redirect.py <out>/<name>.utoc <out dir> [--shadermap <cooked .ushaderbytecode>]`.
- Assets REMOVED from a mod stay in `SavedMods/Cooked/<mod>` and get packed again: delete the mod's Cooked folder before
  cooking after a removal.

## The /Game package redirect
- A kit override is cooked under the MOD's mount, so its package name is `/<mod>/_Stalker_2/...` while its file entry points at
  the vanilla path (`retoc manifest <utoc>` shows both). That is correct, not a bug.
- The game uses it only through a PackageRedirects entry in the container header: `/Game/<path>` id -> `/<mod>/<path>` id, with
  the `/Game` name in the header's name map. The kit's packer writes it; `retoc to-zen` does not. Without it the pak mounts, the
  log is clean, and the game keeps loading its own asset.
- `zen_add_redirect.py` writes the entry for every package whose manifest path is `../../../Stalker2/Content/<path>.uasset`, and
  fills the shader map hashes so the loader preloads the mod's shaders. `--selftest <official override .utoc>` rebuilds an
  official kit-built container header byte for byte (run it after any change to the writer).
- Game log `Invalid container header` for the pak = malformed header: the redirect is dropped.
- A correct override needs all three: the mod's package name, the vanilla file path, AND the redirect. The first two alone look
  right and do not load.

## Cook logs that prove (or disprove) a recompile
| Line | Meaning |
|---|---|
| `Packages Cooked` | the cook finished |
| `Missing cached shadermap for <material> ... compiling` | the material recompiled: your change is in the shaders |
| no such line for a byte-patched material | old shaders from the DDC: renew the StateId and cook again |
| `Failed to compile Material ... Default Material will be used in game` | a permutation failed: the game will draw the grid material; stop (sdk_cook_mod.py does) |
| a `LogNiagara` line with `Error`, `Unknown Function Call` | a Niagara script failed: the system draws nothing in game; stop (sdk_cook_mod.py does) |
| `LogAssetRegistry: Failed to open file for write ... CachedAssetRegistry_N.bin.tmp`, `Failure - 4 error(s)` | the kit editor is open |

## Proving the cooked trio changed
- Material constants are compiled into the shaders and the shader library is compressed: grepping a cooked file for the float
  proves nothing.
- `retoc unpack-raw` the new trio and the previous one and compare: a material change must change the ShaderCodeLibrary chunk.
- To learn what an older build really carries, cook the suspected values with a fresh StateId: a byte-identical shader chunk
  confirms them.

## One mod, several paks
- A second kit mod that the first one references does NOT cook: the mod cook loads only the mod being cooked (log: `will not
  load in Mod Cook Commandlet`) and the reference cooks as NONE. Keep assets that reference each other inside one mod.
- To cut a small pak out of a mod: move the assets that must stay out of it aside for the cook, and cook with
  `-OverrideShaderLibraryName=<own name>_OverrideContent` (run the commandlet by hand; sdk_cook_mod.py always passes the mod's
  name). The small pak's shader library then gets its own chunk id; with the default name it would replace the big pak's library
  at the higher priority. Check with `retoc list` that the only chunk id the two paks share is the package meant to be
  overridden. Restore the mod afterwards.
- Leaving single assets out of a pak after the cook: stalker2-paks.
- A round trip of `retoc to-legacy`, `repak pack --version V11`, `retoc to-zen --version UE5_5` gave back byte-identical
  packages for curve assets, so a curve-only pak can be cut out of a shipped pak without the kit. to-legacy of a mod pak needs
  the game's `global.utoc` and `global.ucas` copied beside it in a temp folder.
- The same round trip CHANGED a Blueprint package (another size, already different at the legacy stage). Never ship a Blueprint
  that went through it: cook it in the kit and compare its export data chunk (`retoc unpack-raw`, the chunk id ending `01`) byte
  for byte with the build that was tested.

## Detached runs, locks and timing
- Never run a cook while the kit editor is open: it holds `%LOCALAPPDATA%/Stalker2/Intermediate/CachedAssetRegistry_*.bin` and
  the cook fails (table above). Never launch the editor while a cook runs.
- A cook started as an agent shell's background job dies when the session ends, and a foreground timeout kills it. Start it
  detached (PowerShell `Start-Process`) and poll its log.
- To start the cook the moment the user closes the kit: a background waiter that waits on the editor's process id
  (`Wait-Process -Id <pid>`), then starts the cook detached. Do not wait on a `tasklist` name match (names are cut to 25
  characters).
- A COLD compile of a big material can take about 11 minutes; the shader workers only start about 9 minutes
  in. A later cook can reuse shaders a failed cook already put in the DDC.

## Smart App Control blocks
Windows Smart App Control blocks unsigned kit binaries, intermittently and a different file each time:

| Symptom | Blocked file | Fallback |
|---|---|---|
| UnrealPak exits 0xC0E90002, no log; UAT says BUILD FAILED after a good cook | `UnrealPak-Json.dll` | retoc + zen_add_redirect |
| UAT fails within seconds, 0x800711C7 | `EpicGames.Perforce.dll` | the cook commandlet directly |
| "ShaderCompileWorker crashed", `Failure=CouldNotBeLoadedByOS`, return code -1058471934 (= 0xC0E90002), editor exits | a shader format or core DLL | retry |
| "An Application Control policy has blocked this file" when starting the editor | the launcher stub | the real editor binary |

- Proof: the Windows event log `Microsoft-Windows-CodeIntegrity/Operational`, events 3077 and 3033 (readable without admin with
  `Get-WinEvent`; filter on the kit's path).
- It is a per-file reputation verdict, not a permanent block: a retry minutes later usually works. A failed run under it is not
  evidence that the pipeline broke.
- Current state (read only): registry `HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy`, value `VerifiedAndReputablePolicyState`
  (0 = off).
- Switching Smart App Control off is the user's decision: it removes a Windows protection against untrusted programs, and whether
  it can be switched back on without reinstalling Windows depends on the Windows version. Offer the fallbacks first.

## Classifier lists and cook rules
From the Stalker 2 modding harness, checked there by extracting the staged containers and reading cooked imports; not re-tested
for this pack.
- `<kit>/Stalker2/SavedMods/PackageClassifier/<mod>/OverridePackages.txt` and `NewPackages.txt` list one package path per line
  (`/<mod>/Runtime/BP_X`). The editor's Package Mod edits these kit copies itself; they are what the cook reads.
- The kit's `GSCCookMod` runs two passes about 2 minutes apart: `-modcooknewcontent` (NewPackages) and `-modcookoverridecontent
  -CookAgainstFixedBase -IgnoreMissingReferences` (OverridePackages).
- The cook takes everything in the mod's `Content` folder, whatever the lists say: keep only what should ship.
- A package in NEITHER list is cooked into BOTH containers: into NewContent under its plugin path, and into the override
  container as a game-path override (`Stalker2/Content/<folder>/<Asset>`). After adding assets to a plugin, add them to
  `NewPackages.txt` and check that the override container holds only what it should.
- A package in BOTH lists is cooked into neither.
- An override-pass Blueprint keeps references only to packages the base game has (or overrides of them): a pin or variable
  pointing at a mod-only asset compiles in the editor and is silently nulled in the cook, with no log line. Data assets differ:
  an override input mapping context may import NewContent `IA_*` actions and works.
- A NewContent Blueprint keeps references to other NewContent, so put logic there.
- `LoadClassAsset_Blocking` on a `/<mod>/...` soft path returned null at runtime: loading mod classes by string is not a way
  around the rule. Loading game-path assets by string works.
- UAT runs one instance per machine: a second cook or `CreatePlainMod` fails at once ("A conflicting instance of AutomationTool
  is already running"). With UAT `GSCCookMod` the harness reports the editor may stay open (5 to 6 minutes a cook); the direct
  commandlet cook in this pack fails if the kit is open, so close it there.
- Dev copies of NewContent have no priority over a release copy (same name, order 3): disable the release copy before testing
  Blueprint changes.

Adapted from the Stalker 2 modding harness by Noah Semus (github.com/noahsemus/stalker2-modding-harness, MIT).
