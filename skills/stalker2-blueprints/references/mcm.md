# Living with other mods; the Mod Configuration Menu (MCM) API

Adapted from the Stalker 2 modding harness by Noah Semus (github.com/noahsemus/stalker2-modding-harness, MIT).
Pak priority and conflict scans: stalker2-paks. Cfg patch files: stalker2-cfg.

## Contents
- Compatibility rules
- Checking who else touches an asset
- MCM: what it is and its API
- How MCM finds and calls a provider
- Kit setup
- Dropdowns
- Retiring dead settings
- Design

## Compatibility rules
- Per asset (and per whole `.cfg` file) the last-mounted pak wins outright. Nothing merges. Every override is a conflict
  with every other mod shipping that asset, and whichever loses loses ALL its edits to it.
- Put logic in NewContent (a ModWorldSubsystem and a mod actor); override only data the mod cannot work without.
- Cfg: patch files only, never whole files. Two patch-file mods collide only when they patch the same field.
- When an override is unavoidable, give the override pak a priority above the usual `_P` / `_10_P` mods (upstream names
  it `zzz_<Mod>_20_P`; the number is what decides, see stalker2-paks) and document the edit so other authors can merge it.
- Never hard-import another mod's assets from the main mod: it then fails to load without that mod. Optional integrations
  go in a separate optional plugin or pak.
- Shared assets seen overridden by more than one mod: `AnimBP_Player`, `BP_Stalker2Character`, `IMC_Exploration`,
  `DA_InputElementsModels` (Controls menu entries), `AnimBP_PlayerWeaponLayer`, `AnimBP_Player_Knife`, weapon
  AnimCollections, `W_GameHUD`, `CoreVariables.cfg` (FOV mods).
- Never override the per-weapon `AnimCollection_fp_*` assets (a big weapon mod overrides 38 of them); per-weapon cfg
  presets would fight such a mod and miss the weapons it adds.
- Players favour fast, skippable animations: keep added animations short and non-blocking, and reuse vanilla montages by
  reference instead of overriding them.
- If other mods must detect yours, offer a **permanent marker asset** with an interface revision in its name and freeze
  the shared block. Never tell others to detect a cook anchor (`/Game/__ModKitWwiseCookAnchor_<Mod>_<timestamp>__`): it
  exists in one build only.
- A NewContent Blueprint that references another plugin's assets cooks and loads when the mod's `.uplugin` lists that
  plugin as a dependency.

## Checking who else touches an asset
- A plain-text scan of installed containers reliably finds the ones that SHIP an asset but under-reports mere
  REFERENCES: cooked packages import other packages by path hash, so a text hit is missing. Read zero hits as "nobody
  overrides it", not "nobody uses it".
- For references, extract the container (`UnrealPak <x>.utoc -Extract <dir>`) and read `scripts/zen_names.py <dir>`
  (names) and `--imports`.

## MCM: what it is and its API
A second menu answers this same API: S2MM (open source) from 1.2.0 on, so a provider written as below also runs for
players who have S2MM and no MCM. What it keeps the same, what differs, and a converter to its own API: stalker2-mod-menus.
Mod Configuration Menu 2.0 is a community settings menu other mods register with: Zone Kit NewContent under
`/ModConfigurationMenu/`, opened in game from its own key. The names below were read from its installed containers.
- `BPI_MCM_API`: `AddUniqueModID`, `RegisterModSetting`, `RegisterDefaultModSetting`, `GetModSetting`, `SetModSetting`,
  `TriggerButtonAction`. Parameters: ModID, SettingID, Category, Type, AuthorName, SettingHoverText,
  Bool/Float/Int/String/Vector/Rotator/Transform values, Keybind, ComboBoxOptions, ButtonText, FloatControllerStepValue,
  header textures.
- `BPI_MCM_SettingsProvider`: `RegisterMCMSettings`, `RegisterMCMDefaultSettings`, `ApplyMCMSettings`,
  `OnMCMButtonPressed`. The provider events' parameter is named `BPI MCM API` (with spaces).
- `Enums/E_MCM_SettingType` (cooked display names, verified): 0 Bool, 1 Int, 2 Float, 3 String, 4 Transform, 5 Vector,
  6 Rotator, 7 ComboBox, 8 Keybind, 9 Button. `GetModSetting`'s int output is `IntegerValue`.

## How MCM finds and calls a provider
- `MWS_MCM` spawns `BP_MCM_Manager` only in `WorldMap_WP`. About 5 s after a load (and on saves) it calls
  `GetAllActorsWithInterface(BPI_MCM_SettingsProvider)` and on each: `RegisterMCMSettings(manager)`,
  `RegisterMCMDefaultSettings`, `ApplyMCMSettings`. So a provider is any spawned actor implementing the interface.
- Every click in the menu calls `SetModSetting` and then `ApplyMCMSettings` on EVERY provider (there is no Apply button).
- `RegisterModSetting` only adds a (ModID, SettingID) not stored yet: the saved value wins. Values persist in the save
  game (`ST_MCM_Save.AllSettings`).
- `GetModSetting` on an unknown setting returns defaults (bool = false): guard Apply with a "registered" flag, or another
  mod's click switches your default-on bool off.
- The menu lists a mod only after `AddUniqueModID` ran this session. If your mod is missing from the menu, check the
  register chain in the export: a node dropped by a paste ends the chain there.
- Mods seen using MCM ship the provider inside their main plugin with the `.uplugin` dependency
  `{"Name": "ModConfigurationMenu", "Enabled": true, "Optional": true}` (some without `Optional`).

## Kit setup
- The kit has no MCM assets. The MCM author's guide links a modder package: an uncooked `ModConfigurationMenu` stub
  plugin (interfaces + enum) and an example mod (`MCM_ModExample1`). Copy both into `<kit>/Stalker2/Mods/` with the editor
  closed. Never select or cook the stub, and never bundle MCM with your mod.
- Copy the "(Message)" API nodes from the example: a node search often picks the wrong ones.
- Feed `ComboBoxOptions` an array with one empty string.

## Dropdowns (types verified in a saved provider Blueprint)
- Type 7 (`NewEnumerator7`), `ComboBoxOptions` = the labels, `ComboBoxSelectedOption` = the index (register: the current
  value; default: the default index). Read back with `GetModSetting`'s `ComboBoxSelectedOption`.
- Paste-text trap: a pin default written right after `PinName` survives for string pins, but the enum pin's (`Type`) is
  reset on paste. Write `DefaultValue=` where the editor does (after the `PinType...` fields, before
  `AutogeneratedDefaultValue`), and never regex-match `DefaultValue=` inside `AutogeneratedDefaultValue=`.
- A setting once registered with the wrong type keeps it from the save: rename its id.

## Retiring dead settings
- MCM stores every setting ever registered in the game save (`MWS_MCM` save data, `BP_MCM_Manager.AllSettings`).
  `RegisterModSetting` only appends, and the API has no remove.
- The menu (`WBP_MCM_ModContainer`) lists ALL saved settings of a mod id, but only for mod ids added this session
  (`ActiveModIDs`, through `AddUniqueModID`).
- So to drop dead settings, register under a NEW mod id: the old id's entries stay in the save, unlisted. The id is the
  menu title, so a trailing space keeps the look ("My Mod "). Saved values of the kept settings reset to their defaults
  once.

## Design
- Talk only to the two interfaces and the enum. A mod that reads MCM's own variables, widgets or save data works with
  MCM itself and nowhere else.
- Keep settings as variables with defaults on the mod's runtime actor, so the mod works without MCM. A small provider
  actor (implements the interface, spawned by the mod's subsystem) registers them and writes them into the runtime actor
  on Apply.
- With the dependency `Optional`, test once with MCM disabled before release (upstream had not tested this). Fallback: a
  separate `<Mod>MCM` plugin as an optional download.
