# Changelog

## Unreleased
- installer: added `--exclude <names or numbers>` for `--install`, added the `zonekit` preset, and kept groups, presets and
  token estimates working when `install.py` runs directly from a source checkout without a prebuilt `catalog.json`.
- stalker2-zonekit: `scripts/niagara_constants.py` reads a Niagara system's module constants straight from the uncooked
  `.uasset`, with the kit closed. references/niagara.md now separates that route from the clipboard route (links, dynamic
  inputs, expression text).
- stalker2-zonekit: added opt-in localhost HTTP editor bridge (`scripts/editor_bridge.py`, `sdk_run.py --bridge*`,
  `references/live-bridge.md`) with fail-closed bearer token auth, single-mod write lock, local `script_root` scope, and
  `tools/build_pack.py` `http.server`/`socketserver` scan coverage.

## 1.0.0 (2026-11-15)
First public release, under the MIT license. 20 skills for STALKER 2 modding, an interactive installer, and an install
routine any AI agent can follow. Merges the Stalker 2 modding harness by Noah Semus, including the documents and tools sdwvit
wrote for it. Stamped for game 2.1 (Steam build 26123434) with Zone Kit 2.1.0.
