# Changelog

## Unreleased
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

## 1.0.0 (2026-11-15)
First public release, under the MIT license. 20 skills for STALKER 2 modding, an interactive installer, and an install
routine any AI agent can follow. Merges the Stalker 2 modding harness by Noah Semus, including the documents and tools sdwvit
wrote for it. Stamped for game 2.1 (Steam build 26123434) with Zone Kit 2.1.0.
