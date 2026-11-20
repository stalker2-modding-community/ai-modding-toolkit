---
name: stalker2-curves
description: Decodes, edits and repacks STALKER 2 cooked curve assets (UCurveFloat and UCurveLinearColor) such as the per-weather light/Curves presets and TimeCoefCurve. Extracts them with retoc, reads and changes keys in place, packs a UE5_5 IoStore trio and avoids the key-layout traps. Use when a change needs a curve value at certain hours, when a curve edit did nothing, overshoots, or dips below zero between keys.
license: MIT
compatibility: Windows. Python 3.8+; retoc and repak (see the pack START_HERE.md)
metadata:
  pack: STALKER 2 AI Modding Toolkit
  pack-version: "1.0.0"
  author: STALKER 2 AI Modding Toolkit contributors
  verified-on: "STALKER 2 Steam build 26123434 (game 2.1), Zone Kit 2.1.0"
---

# STALKER 2 cooked curves

This skill is the file format work for cooked curves: where they are, how to read and change their keys, how to pack
them. It does not say what each weather curve does to the look: prove that in game with a loud value. What TimeCoefCurve
does to game time: stalker2-gamedata.

## Where curves live
- Weather presets: `/Game/light/Curves/<Weather>/<Weather><Name>` (files under
  `Stalker2/Content/light/Curves/<Weather>/`), about 97 curves plus `DA_<Weather>Preset` per weather: Clearly,
  Cloudy, LightRainy, Rainy, Fogy, Thundery, Stormy, CalmBeforeEmission, Emission, Underground. The folder also
  holds `01_InteriorCurves` and a few shared curves at its root. Key times are game hours.
- Game time: `/Game/_STALKER2/GameDesign/Time/TimeCoefCurve`.
- About three quarters are UCurveFloat (one channel); the rest are UCurveLinearColor (four channels: R, G, B, A).

## Workflow
1. **Extract vanilla:** `retoc to-legacy --no-shaders --no-script-objects -f <fragment> <paks> <outdir>`. The
   fragment is a case-sensitive substring of the file path (`Content/light/Curves/Clearly`, or one curve's name);
   add `-d` to count matches without writing.
2. **Decode, check and diff:** `python scripts/decode_curves.py <file.uexp> [...]` prints every key (time, value, tangents, mode
   bytes) as JSON; `--check` flags cubic keys with non-zero tangents and `--diff <vanilla> <mod>` diffs two `.uexp`
   files or matching folders. Imported as a module, its `key_offsets(path)` gives each key's Value offset for in-place edits.
3. **Edit in place, same key count:** overwrite the float32 values (and tangents) at their offsets. The size stays
   the same, so the `.uasset` needs no change. Adding or removing keys changes the export size that the `.uasset`
   records: rewrite with UAssetAPI (atenfyr) or re-save in the Zone Kit (stalker2-zonekit), never by hand.
4. **Pack:** stage the `.uasset` + `.uexp` at their cooked path (`<stage>/Stalker2/Content/light/Curves/<Weather>/`),
   `repak pack --version V11 <stage> <tmp>/<Name>.pak`, then
   `retoc to-zen --version UE5_5 <tmp>/<Name>.pak <outdir>/<Name>_<N>_P.utoc`. The output folder must exist; it
   receives the `.utoc`, `.ucas` and `.pak` stub. Ship only that trio. Priority suffix and conflicts: stalker2-paks.
5. **Verify before the game:** byte-search the `.ucas` for the 4 bytes of a new value, and check the package path
   with `retoc manifest` (run in a temp folder). `to-legacy` cannot read a lone mod `.utoc`.
6. **Test in game** with a loud value first (stalker2-testing). Paks mount at startup: restart the game after
   swapping one.

Read references/format.md before writing or patching curve bytes, adding keys, or when the decoder reports
something unexpected.

## Traps
- **Two-key curves are whole-day edits.** More than a quarter of the weather curves have just two keys per
  channel, at 0 and 24 (or 23.99), nearly always with the same value. Changing a value changes every hour. To shape hours you need
  more keys (a size change, step 3).
- **Zero the tangents on cubic keys.** Keys whose first mode byte is 2 (cubic) carry tangents tuned for vanilla's
  values; new values with old tangents overshoot past both neighbours, and the curve can dip below zero between
  keys (seen in game). Zero all four tangent floats (arrive, arrive weight, leave, leave weight): no overshoot.
  Linear keys (mode 0, most weather curves) ignore tangents.
- **Curves are per weather.** Each weather has its own copy of a curve (`<Weather><Name>`). An edit meant for
  every weather means every weather folder; a weather you skip keeps vanilla.
- The set of curves is fixed: native code applies each curve by name, so a renamed or new curve is ignored.
- Some curves use other time ranges (0 to 1, keys below 0 or past 24): read the key times, never assume hours.
- A channel that serializes no keys is empty and the engine uses its default; some vanilla curves are entirely
  empty.
- Always `--version UE5_5` for `to-zen`; `UE5_3` makes the game log `Invalid container header` (stalker2-paks).
