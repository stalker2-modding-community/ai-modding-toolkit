# Credits

STALKER 2 AI Modding Toolkit, a collaborative project by the STALKER 2 modding community. Unofficial: not affiliated with or
endorsed by GSC Game World, Epic Games, Anthropic or any author below. S.T.A.L.K.E.R. 2 is a trademark of GSC Game World.

## Contributors
| Who | What |
|---|---|
| Noah Semus ([noahsemus](https://github.com/noahsemus)) | Author of the [Stalker 2 modding harness](https://github.com/noahsemus/stalker2-modding-harness) (MIT). stalker2-blueprints, stalker2-animation and the classifier rules in stalker2-zonekit are adapted from it; scripts copied from it carry its notice. |
| sdwvit ([sdwvit](https://github.com/sdwvit)) | Wrote, inside that harness, the documents and tools that stalker2-saves, stalker2-localization, stalker2-voiceover, stalker2-audio, stalker2-publish and stalker2-linux are adapted from, and the cfg reference, gameplay data, combat, console command, cook performance and editor paste material merged into stalker2-cfg, stalker2-gamedata, stalker2-testing and stalker2-zonekit, and the world-actor placement notes in stalker2-zonekit. Author of s2cfgtojson. |
| gjacka ([gjacka](https://github.com/gjacka)) | stalker2-paks, stalker2-cfg, stalker2-gamedata, stalker2-curves, stalker2-zonekit, stalker2-testing, stalker2-crashes, stalker2-updates, stalker2-vortex, stalker2-release, stalker2-workflow, stalker2-mod-setup, stalker2-mod-menus (with its S2MM toolkit scripts), the installer and the build checks. |
| Felicheat ([Felicheat](https://github.com/Felicheat)) | The installer's `--exclude` option and `zonekit` preset. In stalker2-zonekit: the kit path search, older-file support in `niagara_constants.py`, `--pack-cfg`, `uasset_scan.py`, `uasset_summary.py` and `sdk_validate_mod.py`. In stalker2-curves: `--check` and `--diff` in `decode_curves.py`. In stalker2-mod-setup: the optional commit guard. |

## Notice for material from the Stalker 2 modding harness
Every file adapted or copied from the harness says so. This notice applies to all of that material:

    MIT License

    Copyright (c) 2026 Noah Semus

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

## Not included: you get these from their authors
| Who | What | Used for |
|---|---|---|
| sdwvit | [s2cfgtojson](https://github.com/sdwvit/S2CfgToJSON) | stalker2-cfg's tools need it; `npm install` fetches it. Its terms are his: its readme says non-commercial use. |
| KynesPeace / ZunaSW | Kynes Commands Console (Nexus Mods, STALKER 2) | One console mod that works for stalker2-testing. |
| KynesPeace | Mod Configuration Menu (Nexus Mods, STALKER 2) | stalker2-blueprints describes how a mod registers its settings with it; stalker2-mod-menus describes how S2MM answers the same public interface, and its converter reads a mod's calls to those public functions. No code included. |
| ChemBoy1 | [STALKER 2 Vortex extension](https://github.com/ChemGuy1611/ChemBoy1-Vortex-Games) (GPL-3.0) | stalker2-vortex describes how it behaves. No code included. |
| trumank, Archengius | [retoc](https://github.com/trumank/retoc) (MIT) | IoStore containers. |
| trumank | [repak](https://github.com/trumank/repak) (MIT or Apache-2.0) | Plain paks. |
| atenfyr | [UAssetAPI](https://github.com/atenfyr/UAssetAPI) (MIT) | uasset-dump; NuGet fetches it when you build. |
| Audiokinetic | Wwise and its authoring API (WAAPI) | stalker2-audio and stalker2-voiceover describe working with a Wwise project. Not included; its licence terms are Audiokinetic's. |
| Heroic Games Launcher, Valve (Proton) | Heroic, Proton | stalker2-linux describes running the Zone Kit and the game with them. |
| GSC Game World, Epic Games | The game, the Zone Kit, Unreal Engine, Oodle | No game, kit or engine files or code are included. |

## Thanks
- The community guide known as the "Volucris" guide, which the dialog voice steps in stalker2-audio follow.
- rbwadle and Zivaka, who found and explained the temporary effect icon method described in stalker2-gamedata.
