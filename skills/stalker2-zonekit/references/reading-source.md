# Reading GSC's source without the editor

## Contents
- The uncooked editor pak
- uasset-dump
- Compact digests: uasset_summary and uasset_scan
- Settings come from uncooked sources (and the SRGB tag rule)
- A material's real wiring: graph text and mat_t3d
- A saved material: mat_uasset_tree
- Input links by byte offset
- Layout for GUI steps

## The uncooked editor pak
`<kit>/Stalker2/Content/Paks/FullEditor-WindowsModEditor.pak` holds GSC's UNCOOKED assets: full material node graphs,
Niagara systems, source textures and the real property values. It is a plain .pak (about 143,000 entries).
- `repak list <pak> > list.txt` once, then grep the list for the asset name.
- `repak unpack -i <path inside pak> -o <dir> <pak>` pulls single files in seconds. Unpack into a fresh, empty folder.
- `<kit>/Stalker2/Content/GameLite/GameData/` is GSC's commented TEXT cfg tree (how to read it: stalker2-gamedata).
- What you extract is GSC's content: keep it in your working files, never ship or publish it.
- Cooked materials keep no graph: read a GSC material's graph from this pak's uncooked copy, never from the game paks.
- The game paks DO show which materials a Niagara system uses: `retoc to-legacy -f <path fragment>` the system and read the
  name strings. A name ending in `_<number>` is stored as the base name plus a number, so the strings show `M_Name` for the
  package `M_Name_1`.

## uasset-dump
`tools/uasset-dump/` (Program.cs + uasset-dump.csproj) wraps UAssetAPI (atenfyr, MIT). Build it once:
`dotnet build -c Release` inside that folder (needs the .NET 8 SDK). Then:

    tools/uasset-dump/bin/Release/net8.0/uasset-dump.exe <in.uasset> <out.json> VER_UE5_5

- Always pass `VER_UE5_5`: the tool's default engine version is older and misreads the game's assets.
- The pack scripts find it through `scripts/s2paths.py` (env var `S2_UASSET_DUMP`, or `python scripts/s2paths.py --set uasset_dump=<exe>`).
- It reads most uncooked assets. For GSC's older-format ones see the BoolProperty note below (and pass `--old` to
  mat_uasset_tree).
- It does NOT decode material input links (they read 0) or Niagara parameter stores. For links see "Input links by byte
  offset" below; for Niagara values copy the module as text and decode it with
  `scripts/niagara_clipboard.py`.
- Export `SerialOffset` / `SerialSize` give each node's byte range in the .uasset: patch targets are found inside that range.

## Compact digests: uasset_summary and uasset_scan
- `python scripts/uasset_scan.py [<dir>] [--filter <str>] [--cross-mod <mod>] [--limit 50]` parses binary `FPackageFileSummary` / `ImportMap` / `ExportMap` headers plus loose `.cfg` / `.cfg_patch*` files with zero external tools; use it first for quick asset-class and foreign `/Mod/` root triage.
- `python scripts/mat_uasset_tree.py <full .uasset path>` reads saved Material/MI binary bytes directly for parent-chain and parameter hierarchy inspection before opening the GUI.
- `tools/uasset-dump/` (`dotnet build -c Release`) dumps full `.uasset` JSON via UAssetAPI when you need every property name or `SerialOffset` / `SerialSize` byte range.
- `python scripts/uasset_summary.py <file.uasset|file.json> [--material] [--json]` stages a temporary copy, runs `uasset-dump`, and prints only structural imports, Material Instance parameters, Curve keys (flagging cubic non-zero tangents), or `--material` parameters and Custom HLSL line counts instead of raw multi-MB JSON.

## Settings come from uncooked sources
- Texture and asset SETTINGS (SRGB, Filter, CompressionSettings, LODBias, component defaults) must be read from the uncooked
  source in the editor pak, never from the game's cooked file. Cooked properties are unversioned (no property names), so a
  cooked name map cannot show whether a default was overridden. Decoding a texture from cooked bytes with a guessed colour
  space gives wrong pixel values.
- **The SRGB tag rule: no SRGB tag in the asset = SRGB ON** (the engine default). Only an explicit `SRGB False` turns it off.
  This applies to Epic's ENGINE textures too (`<kit>/Engine/Content/...`, loose .uasset files): an engine texture with no
  tag is decoded by the GPU as sRGB, even when GSC's own copy of a similar texture sets it off.
- Check the tag of EVERY texture whose pixel values you rely on.
- Older-format uncooked assets that uasset-dump reads poorly: read a flag such as SRGB from the BoolProperty tag bytes right
  after the property's name index.

## A material's real wiring: graph text and mat_t3d
The reliable way to know what a material does, before any tuning by trial and error:
1. In the kit, open the MATERIAL (`M_...`). An instance (`MI_...`) has no graph. For an override, open the MOD's copy
   (`/<mod>/...`), not `/Game/...`, so the text includes your edits.
2. Click empty graph space, Ctrl+A, Ctrl+C. Paste into a text editor and save the file (UTF-8 or UTF-16 both work).
3. Read it:

       python scripts/mat_t3d.py <graph.txt>                     summary: root inputs, parameters, textures, Custom nodes
       python scripts/mat_t3d.py <graph.txt> root [depth]        formula behind every connected root pin
       python scripts/mat_t3d.py <graph.txt> expr <Name> [depth] formula behind one expression (e.g. MaterialExpressionCustom_4)
       python scripts/mat_t3d.py <graph.txt> uses <text>         which expressions consume those whose label contains <text>

- Every input names the expression that feeds it, with its output index and channel mask, so this is ground truth.
  Shared sub-expressions print once as `@N = ...` and as `@N` after that.
- Stock material function calls come through by name only (`Fn:<name>`); their insides are not expanded.
- What feeds a custom output node (an output that is not a root pin) is not under `root`. Use `expr <that node's name>`.
- Parameters print as `Name[default]`, MPC reads as `MPC.<name>`, textures as `Tex:<param>=<texture>`.
- Named reroutes print unnamed (`NamedReroute`) and are not followed. Resolve them by hand in the graph text: the usage node
  names its declaration node, whose name is the reroute's label and whose input is the real source.
- The text is GSC's material: never ship it or paste it anywhere public.

## A saved material: mat_uasset_tree
`python scripts/mat_uasset_tree.py <full .uasset path> [--old] > out.txt` prints the same kind of formula tree straight from a
saved .uasset: every root pin and custom output node (Volumetric Advanced Output, Single Layer Water Output) walked back, each
Custom node's inputs and code, parameter names and defaults. It reads through a copy, so it works while the kit has the file
open (the way to verify a save before the user closes the kit). `--old` is for GSC's uncooked assets saved by their older
editor. It finds links with the byte-offset rule below and can miss some: it is a first look, and the graph copy read with
mat_t3d is the ground truth when they disagree.

## Input links by byte offset
uasset-dump reports 0 for every input link, but the links are plain int32 FPackageIndex values (1-based export index) at fixed
distances from tags in each node's serialized bytes:

| Input kind | Source expression | Output index |
|---|---|---|
| ExpressionInput (A, B, Alpha, root pins ...) | name tag + 49 | name tag + 53 |
| Custom node input | InputName value + 57 | InputName value + 61 |

- Read the output index as well as the expression: a material function with several outputs feeds different values per index.
- Calibrate on a wire you can see in the editor (one of GSC's own) before trusting a reading on a new asset.
- A heuristic that strides through bytes looking for links has missed real wires that worked in game: use the tag offsets
  above or a graph copy, never a stride guess.

## Layout for GUI steps
uasset-dump gives each expression's `MaterialExpressionEditorX` / `MaterialExpressionEditorY` and each comment box's text and
position. Use them to tell the user where a node sits (inside which comment box, top / middle / bottom, left or right of
which node) when writing click-by-click steps.
