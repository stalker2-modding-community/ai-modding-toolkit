# Changelog

## Unreleased
- stalker2-mod-menus (new): in-game settings for a mod through a mod menu API. S2MM (Stalker 2 Mod Menu, MIT) is a settings page in the
  game's Esc menu with values per save file. Two ways in: S2MM's own API (the toolkit scripts that write a mod's settings Blueprints and pastes
  from a settings file, `s2mm_make.py`) and the MCM API, which S2MM 1.2.0 answers itself so an MCM mod runs with no MCM
  installed (references/mcm-in-s2mm.md: the contract kept, the differences, the type table, what is not covered, a test
  checklist). Also a guide for choosing between the two, the optional MCM-to-S2MM converter (`s2mm_convert_mcm.py`), and
  Blueprint and kit traps proven while building it (typed 0 / false paste defaults dropped, action nodes that look pure,
  the instanced-struct save hook). Verified on build 26123434 with S2MM 1.0.0 to 1.2.0; marked untested: a toolkit button
  reaching the mod's own Branch, MCM Button / String / Transform / Rotator rows under S2MM, and a converter run on a real
  MCM mod.
- stalker2-blueprints: references/mcm.md names S2MM as a second menu that answers the MCM API and adds the rule to talk
  only to the two interfaces and the enum.
- installer: added `--exclude <names or numbers>` for `--install`, added the `zonekit` preset, and kept groups, presets and
  token estimates working when `install.py` runs directly from a source checkout without a prebuilt `catalog.json`.
- stalker2-zonekit: `scripts/niagara_constants.py` reads a Niagara system's module constants straight from the uncooked
  `.uasset`, with the kit closed, adding legacy pre-1012 tag support (verified on UE5 `1008` and `1013`; `1009..1011` share the
  same legacy tag layout in code and are untested on real assets). references/niagara.md separates that route from the
  clipboard route (links, dynamic inputs, expression text).
- shared/s2paths.py: `_detect_kit()` walks parent directories of the script path and working directory for
  `Stalker2/Stalker2.uproject` before reading Epic launcher manifests.
- stalker2-zonekit: `scripts/sdk_code_patch.py --list` prints stored `ScalarParameter` names, defaults and counts;
  `scripts/mat_uasset_tree.py` adds `MaterialAttributesInput` walking; `scripts/sdk_cook_mod.py --pack-cfg` opts in to
  packing `.cfg`/`.cfg_patch*` files into a companion `_Cfg[_N_P].pak` via repak (or cleaning up a stale one).
- stalker2-zonekit: added pure-stdlib `scripts/uasset_scan.py` (binary `.uasset` header/class/foreign-root & `.cfg*` folder scan),
  `scripts/uasset_summary.py` (staged `uasset-dump` digest for Material Instances, Curves and Materials) and `scripts/sdk_validate_mod.py`
  (pre-cook `.uplugin`, `Content/` hygiene and cross-mod reference validator).
- stalker2-curves: `scripts/decode_curves.py` adds `--check` (flags cubic keys with non-zero tangents) and `--diff <vanilla> <mod>`.
- stalker2-mod-setup: added `scripts/mod_guardrail.py` and `init_mod_repo.py --with-hook` for opt-in pre-commit checks
  (blocks secrets, nested `Content/Content/`, and dev dirs in `Content/`; warns on user paths in logs/notes and unknown `Content/` files).
- stalker2-zonekit: added opt-in localhost HTTP editor bridge (`scripts/editor_bridge.py`, `sdk_run.py --bridge*`,
  `references/live-bridge.md`) with fail-closed bearer token auth, single-mod write lock, local `script_root` scope, and
  `tools/build_pack.py` `http.server`/`socketserver` scan coverage.

## 1.0.0 (2026-11-15)
First public release, under the MIT license. 20 skills for STALKER 2 modding, an interactive installer, and an install
routine any AI agent can follow. Merges the Stalker 2 modding harness by Noah Semus, including the documents and tools sdwvit
wrote for it. Stamped for game 2.1 (Steam build 26123434) with Zone Kit 2.1.0.
