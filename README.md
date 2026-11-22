# STALKER 2 AI Modding Toolkit

A collaborative project by the STALKER 2 modding community: skills that teach AI coding agents how STALKER 2: Heart of
Chornobyl modding really works.

20 skills cover paks and IoStore, cfg tables, game data, the Zone Kit, cooking, Blueprint logic, animation, sound and voice,
saves, localization, testing in game, crashes, Vortex and FOMOD, releasing and publishing. They work with Claude Code, Codex,
GitHub Copilot, Cursor, Gemini CLI and other agents that read Agent Skills. Each skill loads only when a task needs it.

Stamped for Steam build 26123434 (game 2.1) with Zone Kit 2.1.0. Most facts were first established on earlier builds; see
stalker2-updates for what was re-checked.

AI agents get things wrong. Every skill tells the agent to prove a change in game before trusting it. Check anything important
yourself.

Two cautions. Numbers and formulas given for the vanilla game (damage, NPC perception, day length and the like) are
modders' measurements and cfg readings on the stamped build, not statements from GSC: check the current tables and test
in game. And this toolkit merges notes from several modders: where two sources disagree, both are shown with their
evidence and the point is open until someone tests it.

Unofficial: not affiliated with or endorsed by GSC Game World. S.T.A.L.K.E.R. 2 is a trademark of GSC Game World.

## Install
Download the zip from [Releases](https://github.com/stalker2-modding-community/ai-modding-toolkit/releases/latest), unzip it,
and follow `START_HERE.md`: double-click `install.bat` for a menu, or tell your agent "Install the STALKER 2 skills from this
folder; follow AGENTS.md."

The installer only copies skill folders. It uses no network, needs no admin rights, and never overwrites a skill it did not
install. See [SECURITY.md](SECURITY.md).

## Contributors
| Who | What they brought |
|---|---|
| [Noah Semus](https://github.com/noahsemus) | The [Stalker 2 modding harness](https://github.com/noahsemus/stalker2-modding-harness): Blueprint paste tooling and traps, game facts, player animation, the mod settings menu notes, cook classifier rules |
| [sdwvit](https://github.com/sdwvit) | cfg reference, gameplay data, combat, console commands, saves, localization, voice-over, Wwise audio, publishing, Linux, cook performance, placing world actors; and [s2cfgtojson](https://github.com/sdwvit/S2CfgToJSON), which the cfg tools run on |
| [gjacka](https://github.com/gjacka) | Paks and IoStore, cfg patch rules and linting, the Zone Kit and cooking, crashes, testing, updates, Vortex, releasing, the installer |
| [Felicheat](https://github.com/Felicheat) | Installer `--exclude` and the `zonekit` preset, kit path search, Niagara reader support for older files, material tools, the optional cfg companion pak, offline asset scanner and summary, pre-cook mod validator, curve check and diff, the optional commit guard |

Everyone whose tools the skills rely on is listed in [CREDITS.md](CREDITS.md).

If you build on this toolkit, please credit the contributors and link back here. That is a request, not a licence condition.

## Contributing
Pull requests are welcome; every one is reviewed before merging. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License
[MIT](LICENSE). Third-party notices: [CREDITS.md](CREDITS.md).
