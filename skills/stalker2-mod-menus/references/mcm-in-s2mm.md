# The MCM API inside S2MM (S2MM 1.2.0 and later)

S2MM answers the Mod Configuration Menu (MCM) API itself, so a mod written for MCM lists in S2MM's menu with no MCM
installed and without a change. How a provider is written against that API: the stalker2-blueprints skill (its MCM notes).
This file is what an MCM-API mod can count on under S2MM. Stamped for build 26123434, S2MM 1.2.0.

## Contents
- How it works
- What stays the same
- What differs
- Types
- Not covered
- Old values, both menus installed, going back
- Testing an MCM-API mod under S2MM
- Proven and untested

## How it works
- S2MM ships a small layer under MCM's plugin name and asset paths (`/ModConfigurationMenu/`): its own `BPI_MCM_API`,
  `BPI_MCM_SettingsProvider` and `E_MCM_SettingType`, an actor that answers the API, and a world subsystem that spawns it.
  It was written for S2MM against the public interface and contains no MCM file.
- A mod's `.uplugin` dependency on `ModConfigurationMenu` is met by that layer: MCM mods loaded with S2MM alone.
- The actor is itself an ordinary S2MM provider. Each MCM setting becomes an S2MM row, so MCM-API mods and S2MM-API mods
  sit in the same tab and the same store.

## What stays the same
| Call | Under S2MM |
|---|---|
| provider discovery | any spawned actor implementing `BPI_MCM_SettingsProvider`; it gets `RegisterMCMSettings`, `RegisterMCMDefaultSettings`, then `ApplyMCMSettings`, in that order |
| `RegisterModSetting` | adds the row; a value already stored for it wins over the value passed in |
| `RegisterDefaultModSetting` | the value Reset and the Default hint use (without it: the registered value) |
| `GetModSetting` | the current typed value; an unknown (ModID, SettingID) returns false, 0 and empty, so keep the "registered" guard |
| `SetModSetting` | changes the stored value and the open menu, then applies |
| `ApplyMCMSettings` | sent to EVERY provider after any change; re-read all your settings each time |
| `TriggerButtonAction`, a button press | `OnMCMButtonPressed(ModID, SettingID)` on every provider |
| Keybind | the mod reads the key's short display name, as under MCM |

ModID is the page name, SettingID the row label, Category a section heading, SettingHoverText the description, AuthorName
the "by" line.

## What differs
- **Timing.** S2MM looks for providers from 6 s after the world starts, then every 3 s for the whole session. A provider
  is asked once per session, when first seen; one spawned late is still picked up. Register everything inside
  `RegisterMCMSettings`.
- **Where values live.** In S2MM's store, per save file, written at once (no game save needed). A new game starts from
  the values of the save made last, not from the mod's registered values.
- **One apply per frame.** A load pushes every stored value, then `ApplyMCMSettings` runs once, not once per value.
- **Keys.** The player can pick any key except Esc and Backspace.
- **Looks.** S2MM draws its own page: `ModHeaderTexture` and `CategoryHeaderTexture` are not shown. Floats have no range,
  so they are number boxes stepped by `FloatControllerStepValue` (0.1 when it is 0).

## Types
| MCM type | S2MM row | State |
|---|---|---|
| Bool | checkbox | proven in game |
| Int, Float | number box | proven in game |
| ComboBox | `< option >` selector; the value is the index | proven in game |
| Vector | three number boxes | proven in game |
| Keybind | key picker | proven in game |
| Button | button | built, not tried in game |
| String, Transform, Rotator | a read-only line; the player cannot change it | built, not tried in game; do not rely on it |

## Not covered
- A mod that goes past the two interfaces and the enum: reading MCM's own variables or save data from the API actor,
  using MCM's widgets, or reaching MCM's objects from outside Blueprint. Those parts are not in S2MM's layer, so that
  mod's settings do not list. S2MM's layer also loads in MCM's place whenever S2MM is installed, so such a mod does not
  get MCM beside S2MM either (by design; not tried in game).
- Finding the API actor by class (`BP_MCM_Manager`) works: the class exists at the same path.
- The rule for authors: talk only to `BPI_MCM_API`, `BPI_MCM_SettingsProvider` and `E_MCM_SettingType`. Such a mod runs
  under both menus.

## Old values, both menus installed, going back
- **Old values.** The first time a save that holds MCM's data is loaded under S2MM, the stored values of the mods
  installed at that moment are taken over. Saves written under S2MM carry no MCM data.
- **Both installed.** S2MM's layer is packed with the `_P` name tail, mounts after MCM's files and answers the mods.
  One menu, each mod listed once. MCM can stay installed or be removed.
- **Going back to MCM.** Saves load. MCM starts those mods from their defaults again, and in our one run its menu stayed
  empty for about half a minute after the load.
- Mod page wording that fits: "Requires MCM, or S2MM 1.2.0 or later."

## Testing an MCM-API mod under S2MM
1. S2MM 1.2.0+ installed, MCM switched off. Load a save, wait 10 s, Esc > MODS > S2MM tab: the mod is listed.
2. Change one row of every type the mod uses: the mod reacts at once. For a key row, pick a key whose long and short
   names differ (Page Up, a punctuation key) and press it in game.
3. Hold the reset key on a changed row: it returns to the default the mod declares, and the Default hint shows it.
4. Reload the save without saving: the changed values held. Load another save: its own values.
5. A save from the mod's MCM days: its old values show after the first load.
6. Once more with MCM alone, to confirm nothing in the mod now depends on S2MM.

## Proven and untested
- Proven in game (build 26123434, S2MM 1.2.0, four published MCM mods, MCM not installed): listing, the row types
  marked above, changes reaching the mod, values per save file, old MCM values taken over on two saves, Reset using the
  declared default, any-key rows with short key names, both menus installed, leftover files of the older S2MM bridge,
  and removing S2MM again.
- Built and read back from the cooked Blueprints, not tried in game: Button rows, String / Transform / Rotator rows,
  `SetModSetting` called by a mod, a provider spawned minutes into a session.
- Not tried at all: a mod that goes past the interfaces (see "Not covered").
