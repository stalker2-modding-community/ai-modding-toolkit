---
name: stalker2-mod-menus
description: "Gives a STALKER 2 mod an in-game settings page through a mod menu API: S2MM's own (Stalker 2 Mod Menu, MIT; Esc > MODS, values per save file) or the MCM API (Mod Configuration Menu), which S2MM also answers so an MCM mod runs without MCM. Covers choosing one, the S2MM toolkit that writes the settings Blueprints, converting from MCM, and paste traps. Use when a mod needs player settings, must work under S2MM or MCM, or a value never arrives."
license: MIT
compatibility: Windows. STALKER 2 Zone Kit with S2MM's kit package; Python 3.8+; PowerShell
metadata:
  pack: STALKER 2 AI Modding Toolkit
  pack-version: "1.0.0"
  author: STALKER 2 AI Modding Toolkit contributors
  verified-on: "STALKER 2 Steam build 26123434 (game 2.1), Zone Kit 2.1.0, S2MM 1.0.0, 1.1.0 and 1.2.0"
---

# In-game settings for a mod: the S2MM and MCM APIs

Two community menus give a mod a settings page: **S2MM** (Stalker 2 Mod Menu), which adds MODS under OPTIONS in the Esc
menu, and **MCM** (Mod Configuration Menu). A mod reaches players through S2MM's own API or the MCM API; S2MM answers
the MCM API itself from 1.2.0 on, with no MCM installed. Writing an MCM provider, Blueprint basics and pastes:
stalker2-blueprints. Cooking: stalker2-zonekit.

## Which API
| | S2MM's own API | MCM API |
|---|---|---|
| Players need | S2MM | MCM, or S2MM 1.2.0+ alone |
| The kit needs | S2MM's kit package | MCM's modder package (stalker2-blueprints, its MCM notes) |
| You write | a settings file and one script (Route A), or by hand (Route B) | the provider by hand |
| Rows | toggle, slider, number, choice, colour, key, button, header, info | bool, int, float (no range), dropdown, vector, key, button |

- A new mod: S2MM's API. A mod that must also serve MCM players, or an existing MCM mod: stay on the MCM API; it lists in
  S2MM unchanged. Use one API per mod.
- An MCM mod under S2MM (what is kept, what differs, limits, a test list): references/mcm-in-s2mm.md.

## What is proven and what is not (build 26123434)
- Proven in game, S2MM's API (1.0.0 to 1.2.0): registering from a mod actor; every control type; values at load and on
  change, per save file; a mod built on S2MM loads without S2MM (no settings, no crash); saves made with S2MM load after
  it is removed; `s2mm_make.py` made a working demo mod; a mod made before 1.2.0 runs unchanged on 1.2.0.
- Proven in game, MCM API (1.2.0): published MCM mods list and work with S2MM alone, MCM not installed.
- Not observed: a toolkit button press reaching the mod's own Branch. NOT yet played: `s2mm_convert_mcm.py` on a real MCM
  mod. Say so to the user and test first.

## You need (S2MM's own API)
1. **S2MM's kit package** (the `S2MM` folder from the S2MM Modder Toolkit download) copied into
   `<Zone Kit>\Stalker2\Mods\S2MM`. The mod builds against it; it is never packed into the mod.
2. The mod's `.uplugin` lists S2MM: `"Plugins": [ { "Name": "S2MM", "Enabled": true } ]`.
3. Players install S2MM. Say so on the mod page. Without it the mod runs on its defaults.

## Route A: the toolkit (recommended)
Scripts in `scripts/` (the same files as in the S2MM Modder Toolkit).
1. Write `s2mm_settings.json` next to `scripts/s2mm_make.py` (format: references/s2mm-api.md, "Settings file"). Check it outside the
   kit: `python scripts/lib/s2mm_settings.py check s2mm_settings.json`.
2. Kit open, the mod picked: **File > Execute Python Script** > `s2mm_make.py` (it also runs headless; see stalker2-zonekit).
   It makes `/<Mod>/S2MM/BP_<Mod>_S2MM` (the settings actor, one variable per setting) and `BP_<Mod>_S2MMSubsystem` (the
   starter), adds the dependency, and writes `out/<Mod>/`: two pastes, a copy window and `SESSION_GUIDE.md`.
3. The user follows `SESSION_GUIDE.md`: open `BP_S2MM_Manager` first (so pasted references resolve), then each paste goes
   into a CLEARED Event Graph, compile, save.
4. Package. In game: Esc > MODS > S2MM tab > the mod.
5. Settings changed later: edit the file, rerun the script, redo the first paste.

## Route B: by hand
The API is on `/S2MM/Core/BP_S2MM_Manager` (Get Actor Of Class). Full table and click-by-click steps: references/s2mm-api.md.
- An actor implementing `/S2MM/API/BPI_S2MM_Provider` (Class Settings > Implemented Interfaces; Python cannot add an
  interface in this kit) gets **S2MM_Register** (`S2MM_AddMod`, then one `S2MM_Add*` call per setting) and
  **S2MM_OnValue** (read `LastMod`, `LastID`, `LastValue`, `LastBool`, `LastInt`, `LastFloat` on the manager).
- `S2MM_Get(ModID, SettingID)` answers at once (`Result*` on the manager), even before the mod registered.
- A `ModWorldSubsystem` keeps the actor alive (spawn it on Tick when not valid). S2MM looks for providers every 5 s.

## Route C: an existing MCM mod
First answer: change nothing. On S2MM 1.2.0+ it lists in the S2MM tab as it is and still serves MCM players.
Converting is optional (gains ranges, sliders, info lines; players then need S2MM and start from defaults):
`scripts/s2mm_convert_mcm.py` reads the mod's Blueprints (read only) and writes `out/<Mod>/s2mm_settings.json` plus
`conversion_report.md`; then Route A, swap the reads, remove MCM. Details: references/convert-mcm.md.

## How values flow (read when "the value never arrives")
- On load, S2MM sends every stored value to its mod through S2MM_OnValue, and again on each change. A setting with no
  stored value sends nothing on load: the variable keeps its default (`s2mm_make.py` sets it from the file).
- Values are kept per save file and written at once (no game save needed). A new game, or a save from before S2MM,
  starts from the values of the save made last.
- MCM-API mods use the same store; they get values through `ApplyMCMSettings` and `GetModSetting`.
- The load push re-sends a button's stored value (`0`): a button handler must check `LastValue == "press"`.
- `ModID` and setting ids are the storage keys: keep them the same forever, or players' values reset.

## Traps (references/blueprint-traps.md)
- A typed `0` or `false` pin default is DROPPED on paste and the function's own default wins: use `Max(k, k)` for an int
  literal and `Not(true)` for false. Read every typed default back from an export.
- Some "Get" nodes are action nodes in this kit: written as pure they are dropped and read 0. A class pin default
  survives a paste only if that asset is loaded. Key events on a mod actor never fire beside mods that consume every key:
  poll `PlayerController.WasInputKeyJustPressed` on Tick.

## Check before handing over
1. Re-export each pasted Blueprint (the T3D exporter in stalker2-blueprints): compare node kinds and counts with the
   paste, list class pins with no default and no link.
2. In game: change each setting, reload without saving, confirm the value held; load another save, confirm its own values;
   a button fires on press and NOT on load.

## References
- references/s2mm-api.md: the settings file, setting types, the full S2MM API, by-hand steps, per-save details.
- references/mcm-in-s2mm.md: the MCM API inside S2MM: contract kept, differences, types, limits, test checklist.
- references/convert-mcm.md: type mapping, what the converter cannot read, swapping reads, removing MCM.
- references/blueprint-traps.md: paste and kit facts proven while building S2MM.
