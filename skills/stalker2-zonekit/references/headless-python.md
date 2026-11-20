# Headless editor Python

## Contents
- Running a script
- A kit mod without the GUI
- A GSC asset into a mod without the GUI
- Material graphs
- Material instances
- Blueprint class defaults
- What it cannot do
- Notes from the modding harness

With the kit CLOSED, editor Python run as a commandlet reads anything and edits and saves assets that are in a mod folder. No GUI
session is needed for those edits. What it cannot do is listed below.

## Running a script
`python scripts/sdk_run.py <script.py>` runs editor Python with no GUI (detached; poll with `--wait`; `--launch` returns at once).
Output is the `LogPython:` lines of the editor log. Startup costs minutes, so batch the work into one script.
When the GUI editor is already open, you can instead start the opt-in localhost HTTP bridge (`scripts/editor_bridge.py`) and dispatch tasks via `python scripts/sdk_run.py --bridge-action ...` or `--bridge <script.py>` without restarting the editor (pass `mod='<ModName>'` to allow `set_mi_params` writes; live GUI testing is still pending, only mock-UE tests have run so far).
- If the launcher stub is blocked, the Cmd exe runs the same job (about 150 s with the kit closed):
  `<kit>/Stalker2/Binaries/Win64/Stalker2ModEditor-Win64-Shipping-Cmd.exe "<kit>/Stalker2/Stalker2.uproject" -run=pythonscript
  -script="<file>" -ddc=ModEditorInstalledDerivedDataBackendGraph -unattended -NoLogTimes -abslog=<log>`.
- The process exits 1 even on success: read the log, or a report file your script writes, never the exit code.
- Wait on the process id (Get-Process), not on a `tasklist` match: tasklist shows image names cut to 25 characters.
- Mod content: call `unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(['/<mod>/'], True)` first, or every
  `load_asset` of a mod asset fails with "could not be found in the Asset Registry".
- A mod asset's path is `/<mod>/` plus the GSC path: `/<mod>/_Stalker_2/...`.
- Before saving, read back what you changed (code, wires, values) and stop without saving on any mismatch. Keep a backup of the
  mod's assets in `<repo>`.

## A kit mod without the GUI
`CreatePlainMod.bat <name>` is the normal way. A mod was also made by hand, with no GUI and no UAT:
1. Create `<kit>/Stalker2/Mods/<mod>/` and copy in another plain mod's `.uplugin`, `Resources` folder and
   `Content/<that mod>.uasset` (its GameFeatureData).
2. Replace the other mod's name with the new one in all three: file names and file contents (the `.uasset` by a byte replace).
3. The new name must be EXACTLY as long as the source mod's name, or the data asset does not survive the byte replace.
Cook and pack as usual; the redirects are written.
- The harness says the opposite about that asset: do not duplicate another mod's GameFeatureData, because its actions carry that
  mod's names and are not editable from Python. Both are reported as tested. The by-hand copy changes the names by the byte
  replace, so check that no occurrence of the old name is left in the file. Caution: this point is open; test it before relying on either statement.

## A GSC asset into a mod without the GUI
A headless run cannot check a `/Game` asset out (no mod is selected). The checkout can be reproduced instead:
1. Pull the uncooked `.uasset` out of the kit's editor pak (`repak unpack -i <entry> -o <dir> <pak>`) and put it at
   `<kit>/Stalker2/Mods/<mod>/Content/<same path as in the game's Content>`.
2. In a headless script: scan the mod, `load_asset('/<mod>/<path>')`, then `unreal.EditorAssetLibrary.save_loaded_asset(asset)`.
   The save rewrites the package name to the mod's, like a GUI checkout.
Edits can follow in the same run. Two GSC materials were edited, cooked and packed this way with no kit session.

## Material graphs
On a material in the mod (a GSC material copied in as above included), these ran and saved:
- `unreal.MaterialEditingLibrary`: `create_material_expression` (Custom, parameter, CollectionParameter, Multiply),
  `connect_material_expressions(src, '', dst, '<input name>')`, `connect_material_property`,
  `get_material_property_input_node`, `get_inputs_for_material_expression` (reads the wires back), `recompile_material`.
- Plain material properties, for example the translucency pass.
- A Custom node's `code` and `inputs` (a list of `unreal.CustomInput`, each with an `input_name`), on an existing node as well.
  Custom nodes are found with `unreal.ObjectIterator(unreal.MaterialExpressionCustom)` filtered by the asset's path.
- Save with `unreal.EditorAssetLibrary.save_loaded_asset`. Edit, cook and pack took about 2.5 minutes a round.
- `MaterialExpressionCollectionParameter.parameter_id` is NOT exposed. Set `collection`, then `parameter_name`: that resolves the
  id. Prove it in the saved file: the parameter's 16 id bytes (from a uasset-dump of the collection) must be there.
- A master material that uses Material Attributes cannot be walked from kit Python: its `MaterialProperty` enum has no
  WorldPositionOffset or MaterialAttributes entry. Only a graph copy from the GUI shows that wiring.
- `recompile_material` runs on mod materials. An earlier report of it crashing dates from before mod content could be loaded.

## Material instances
On an instance in the mod:
- Static switches: `set_material_instance_static_switch_parameter_value`, then `update_material_instance`.
- Scalars: `set_material_instance_scalar_parameter_value`. It returns False even on success: read the value back.
- Re-parenting: `set_material_instance_parent`.
- Base property overrides: the instance's `base_property_overrides` (tested with `override_opacity_mask_clip_value` and
  `opacity_mask_clip_value`).
- `duplicate_asset` of a GSC master material into the mod, then nodes wired in the copy as in the section above.

## Blueprint class defaults
Graph nodes are out of reach, class defaults are not:

    cdo = unreal.get_default_object(bp.generated_class())
    value = cdo.get_editor_property('<property>')      # an array of structs worked
    # change value
    cdo.set_editor_property('<property>', value)

Then save the Blueprint. The same defaults can be byte patched in the uncooked `.uasset` when their floats are unique in the file.

## What it cannot do
- Save a `/Game` asset: the save crashes (a commandlet has no mod selected, so the checkout has nowhere to go). Use the copy
  route above.
- Blueprint graph nodes: they cannot be created from Python. Paste them (stalker2-blueprints).
- Niagara: no edit access. Custom HLSL nodes are not exposed, `emitter_handles` is not exposed, and there are no compile or
  save methods. The kit is a shipping build, so a C++ helper plugin is not an option.
- A Level Sequence's Niagara parameter track: Python cannot set the track's parameter.
- Live control of the OPEN kit needs Project Settings > Plugins > Python > Enable Remote Execution: a kit config change, the
  user's call. Editor MCP bridges wrap this same Python and add nothing for Niagara.

## Notes from the modding harness
From another team's headless runs; not re-tested for this pack.
- Its runner passes `-run=pythonscript -script=<file> -unattended -nosplash -stdout -NoShaderCompile` (about 4.5 minutes).
- It reports that a headless run mounts neither the plugin nor its assets into the registry. Its scripts first activate the plugin
  when `/<Mod>/<Mod>` does not exist (`unreal.GameFeaturesSubsystem.load_and_activate_game_feature_plugin('file:<full .uplugin
  path>', unreal.GameFeaturePluginLoadComplete())`), then call `scan_paths_synchronous`. In this pack's runs the scan alone was
  enough. If a mod asset still does not load after the scan, activate the plugin as well.
- Close the editor for scripts that move, rename or save assets: a second instance makes the commandlet exit before the script.
- `delete_asset` on a never-saved temporary asset crashes the commandlet: leave it unsaved instead.

Adapted from the Stalker 2 modding harness by Noah Semus (github.com/noahsemus/stalker2-modding-harness, MIT).
