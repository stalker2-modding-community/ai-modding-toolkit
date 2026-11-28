# S2MM API, settings file and by-hand steps

## Contents
- Settings file
- Setting types
- The API on BP_S2MM_Manager
- By hand, click by click
- Reading values in the mod
- Where values live
- Troubleshooting

## Settings file
`s2mm_settings.json`, read by `scripts/s2mm_make.py` (check it: `python scripts/lib/s2mm_settings.py check <file>`).
```json
{
  "mod": "MyMod",
  "id": "mymod",
  "name": "My Mod",
  "author": "Me",
  "group": "S2MM",
  "settings": [
    {"id": "h_main", "type": "header", "label": "Main"},
    {"id": "Enabled", "type": "toggle", "label": "Enabled", "desc": "Turns it on or off.", "default": true},
    {"id": "Strength", "type": "slider", "label": "Strength", "desc": "How strong.", "default": 1.5, "min": 0, "max": 5, "step": 0.5}
  ]
}
```
| Field | Meaning |
|---|---|
| `mod` | the kit mod folder name (letters, digits, `_`) |
| `id` | S2MM's id for the mod; values are stored under it, keep it forever. Default: `mod` in lower case |
| `name` | shown in the mod list |
| `author` | shown in the description column |
| `group` | the tab: `S2MM` |

Every setting: `id` (becomes a variable name: a letter, then letters, digits, `_`; keep it forever), `type`, `label`, `desc`
(shown in the description column).

## Setting types
| `type` | Players see | Extra fields | Variable on the settings actor |
|---|---|---|---|
| `header` | a section heading | | none |
| `toggle` | a checkbox | `default` true / false | Boolean |
| `slider` | a slider with decimals | `min`, `max`, `step`, `default` | Float |
| `intslider` | a slider with whole numbers | `min`, `max`, `step`, `default` | Integer |
| `number` | a number box, decimals, no range | `default`, `step` (0.1) | Float |
| `intnumber` | a number box, whole numbers, no range | `default`, `step` (1) | Integer |
| `choice` | a `< option >` selector (Left / Right) | `options` (list), `default` (index, 0 = first) | Integer (index) |
| `color` | three number boxes R, G, B and a colour square | `default` `[255, 255, 255]` (0 to 255) | Vector |
| `info` | a line of text | `text` | none |
| `button` | a button | `text`: what it says (`PRESS`) | none; the made graph has a Branch for it |
| `key` | a key picker: A / Enter, then the key | `default`: key name, e.g. `"F6"` | String (the key's name) |

- The gamepad moves a number by `step` per D-pad press; give numbers a step above 0.
- A key picker catches F1 to F12, `~`, Insert, Home, End, Page Up, Page Down, Num 0 to 9, Multiply, Add, Subtract, Divide,
  Decimal, Pause, Scroll Lock. It stores the long display name (`Page Up`, `Num 0`) and `~` for the tilde key. To use it,
  poll candidate keys and compare `Key Get Display Name` (Long Display Name on) with the variable.
- S2MM 1.1.0+: the player can clear a key with Delete; the variable then holds `None` (no key). No key has that name, so the
  compare never matches: treat `None` as "no key".
- Colours: prefer 0 to 255 per part (`[255, 128, 0]`): whole numbers 0-255 in the menu. 0-1 colours (S2MM 1.0.0's example)
  still work and keep decimals. A row whose label says colour / color / RGB / tint gets a colour square (1.1.0+). Divide by 255
  for an engine colour. A `choice` above the colour in the same section with an option named `Custom` switches to Custom when
  the player edits the colour.
- S2MM's own words (Default, Option n of m, Reset all, the hint bar) follow the game's language (1.1.0+); the mod's labels,
  descriptions and options show as written.

## The API on BP_S2MM_Manager
| Call / value | Use |
|---|---|
| `BPI_S2MM_Provider` (interface) | events `S2MM_Register` (add settings) and `S2MM_OnValue` (a value arrived) |
| `S2MM_AddMod(Provider, ModID, Name, Author, Group)` | once, in S2MM_Register, before the settings |
| `S2MM_AddHeader / AddToggle / AddSlider / AddIntSlider / AddChoice / AddInfo / AddColor` | one per setting, in display order; Provider = self; choice options as `A|B|C` |
| `S2MM_AddSetting(Provider, ModID, SettingID, Type, Label, Desc, Default, Min, Max, Step, Options)` | the long form; Type header, toggle, int, float, choice, info, vector, button, key. Button: Default `0`, Options = its text. Key: Default = key name |
| `LastMod, LastID, LastValue, LastBool, LastInt, LastFloat` | read inside S2MM_OnValue |
| `S2MM_Get(ModID, SettingID)` then `Result, ResultFound, ResultBool, ResultInt, ResultFloat` | read any value at any time |

A number box with no range: AddSlider / AddIntSlider with Min -1000000, Max 1000000. A colour arrives as `LastValue` `"x,y,z"`; a key as its name, or `None` when cleared.

## By hand, click by click
1. `.uplugin`: add `{ "Name": "S2MM", "Enabled": true }` to `"Plugins"`. Restart the kit.
2. Content Browser, in the mod: folder `S2MM` > right-click > Blueprint Class > Actor, `BP_<Mod>_S2MM`.
3. Class Settings > Implemented Interfaces > Add > `BPI_S2MM_Provider`. Compile.
4. Variables: one per setting (types above) plus `Manager` (BP S2MM Manager, object reference). Compile, set defaults.
5. Event S2MM Register > Get Actor Of Class (BP_S2MM_Manager) > Cast > Set Manager > S2MM_AddMod > one Add call per setting.
6. Event S2MM On Value > Branch (LastMod == ModID) > per setting: Branch (LastID == id) > set the variable from LastBool /
   LastInt / LastFloat / LastValue. A colour: Parse Into Array on `,`, String To Float per part, Make Vector; index the parts
   with node outputs, not typed 0 (a typed 0 is dropped on paste; SKILL.md, Traps). A button: Branch LastID == id, then Branch
   LastValue == `press`.
7. Blueprint Class > ModWorldSubsystem, `BP_<Mod>_S2MMSubsystem`: On Initialized > Set Tick Enabled (true); On Tick > if a
   `Provider` variable is not valid: Spawn Actor From Class (the actor) > Set Provider.
8. Compile, save, Package.

## Reading values in the mod
- Get Actor Of Class (`BP_<Mod>_S2MM`) > Cast > read the variable named like the setting id.
- Or the manager's `S2MM_Get` (answers from the stored value even before the mod registered).
- React to a change: add nodes after the variable set inside S2MM_OnValue.

## Where values live
- One global file: `%LOCALAPPDATA%\Stalker2\Saved\SaveGames\S2MM_Settings.sav` (SaveGameToSlot).
- Per save: the ModWorldSubsystem save hook writes one string into each game save (`S2MMID=<id>@@keys##values`). Every save
  gets a new id. After a load, changes are written at once to the global file under that id, so they hold across reloads
  without saving the game.
- Lookup on load: this save id's values in the global file, then the values inside the save, then the last-used value.
- Removing S2MM: saves still load (the save entry wraps an engine struct that always exists). Tested.

## Troubleshooting
| You see | Cause / fix |
|---|---|
| "Could not find a variable", empty class boxes after a paste | S2MM was not loaded: open BP_S2MM_Manager (Ctrl+P), clear, paste again |
| The mod is not in Esc > MODS | S2MM not installed in the game; the starter missing; not packaged |
| Values reset after an update | the mod id or a setting id changed |
| Two S2MM_Register events, compile error | the settings actor's old graph was not cleared before the paste |
| A button fires when a save loads | the handler does not check LastValue == `press` |
| Unused variables in the settings actor | it began as a copy of S2MM's own actor; harmless, can be deleted |
| MODS missing from the Esc menu | another mod replaces the Esc menu's button list (`PauseRootButtonData`), which S2MM edits |
