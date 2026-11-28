# Converting a mod made for MCM to S2MM

MCM's API and how it calls providers: the stalker2-blueprints skill (its MCM notes). The converter uses only MCM's public
function names and reads only the user's own mod. Converting is optional: see "Convert or not".

## Contents
- Convert or not
- Running the converter
- Type mapping
- What it cannot read
- After the conversion

## Convert or not
- **Keep the MCM API:** since S2MM 1.2.0 the mod works in S2MM as it is, with no MCM installed. It lists in the S2MM tab
  with S2MM's controls, the values players set in MCM before are taken over on the first load, and the mod keeps working
  for players who use MCM. Nothing to change. Not covered: a mod that hooks into MCM's memory instead of using its
  interface.
- **Move to S2MM's API:** ranges and sliders for numbers, info lines, no MCM dependency. The mod then needs S2MM, and
  players start from the mod's defaults (the converted mod has new ids): say so in the changelog.

## Running the converter
1. Back up the mod folder. S2MM's kit package must be in the kit (SKILL.md, "You need"); MCM's kit files too, as the mod
   already needs them to compile.
2. Write the mod folder name in `scripts/s2mm_convert.txt` (one line), or set `S2MM_CONVERT_MOD`.
3. Kit open with the mod: File > Execute Python Script > `s2mm_convert_mcm.py`. Last line of
   `out/<Mod>/s2mm_convert_report.txt`: `ALL DONE` or `FAILED` with the reason.
4. Read `out/<Mod>/conversion_report.md`: Converted, Not converted, Notes, Reads to swap.

How it works: exports each Blueprint of the mod as T3D, finds `RegisterModSetting` calls (K2Node_Message or CallFunction),
reads each pin's typed value (option lists also from a Make Array of typed values; anything else wired in is reported as
computed), and records `GetModSetting` reads with the outputs used.
One header per MCM category. Several MCM mod ids in one mod: all go under one S2MM mod (a note says so).

## Type mapping
| MCM type (E_MCM_SettingType) | S2MM type | Notes |
|---|---|---|
| Bool | `toggle` | |
| Int | `intnumber` | MCM numbers have no range; for a slider set `intslider` with `min` / `max` |
| Float | `number` | keeps MCM's controller step (0.1 if none); `slider` with `min` / `max` for a slider |
| ComboBox | `choice` | variable = option index; `|` in an option becomes `/` |
| Vector | `color` | Vector variable |
| Rotator | `color` | pitch, yaw, roll as a Vector; make a Rotator where used |
| Button | `button` | a press reaches S2MM_OnValue with LastValue `press`; move the mod's MCM press logic to the made Branch |
| Keybind | `key` | the variable is the key's NAME (String). The default is left empty and the settings check stops until it is written. `None` = the player cleared it |
| String, Transform | not converted | S2MM has no text field or transform setting |

## What it cannot read
- A setting id, type, default or option list wired from other nodes (worked out at run time). The report names each one.
  Write those values into the settings file by hand.
- Settings registered from C++ or from another plugin.

## After the conversion
1. Check `s2mm_settings.json` (labels, defaults, options), copy it next to `s2mm_make.py`, run it (SKILL.md, Route A).
2. Swap each read in the report: Get Actor Of Class (`BP_<Mod>_S2MM`) > Cast > the variable with the setting's name, wired
   where the MCM value went; delete the MCM node. Or `S2MM_Get` on the manager.
3. Remove the MCM interface (Class Settings > Implemented Interfaces > trash), the remaining MCM calls, and the
   `ModConfigurationMenu` entry from the `.uplugin`. Restart the kit, compile, Package.
4. Mod page: S2MM is the requirement now, MCM is not. Players who use MCM lose the settings page.

Not yet done on a real published MCM mod: the converter was built against MCM's public names and checked on a test
Blueprint with Bool, Int, Float, ComboBox, Vector, String and Keybind settings (Button and Rotator not in that test).
Treat its first real run as a test and read the report line by line.
