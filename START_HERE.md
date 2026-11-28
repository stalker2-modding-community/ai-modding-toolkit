# STALKER 2 AI Modding Toolkit 1.0.0

A collaborative project by the STALKER 2 modding community. Contributors: CREDITS.md.

A set of skills that teach AI coding agents (Claude Code, Codex, GitHub Copilot, Cursor, Gemini CLI and others)
how STALKER 2: Heart of Chornobyl modding really works: paks and IoStore, cfg tables, the Zone Kit, cooking,
testing in game, crashes, Blueprint logic, animation, sound and voice, saves, localization, Vortex and FOMOD, releasing
and publishing. Each skill loads
only when a task needs it, so the pack costs about 100 tokens per skill until then.

Stamped for STALKER 2 Steam build 26123434 (game 2.1) with Zone Kit 2.1.0. Most facts were first established on earlier builds; what
was re-checked on 2.1 is in stalker2-updates, references/build-history.md. After a game update, ask your agent to
run the stalker2-updates skill before trusting a fact that touches what changed.

AI agents get things wrong. Every skill tells the agent to prove a change in game before trusting it. Check
anything important yourself before you ship it. Numbers given for the vanilla game are modders' measurements and cfg
readings on the stamped build, not statements from GSC. Where two sources in a skill disagree, both are shown and the
point is open until tested.

## What is inside

| Group | Skills |
|---|---|
| Start here | stalker2-workflow (how the agent should work with you), stalker2-mod-setup (learns your own mods), stalker2-updates (game update checks), stalker2-linux |
| Game files and data | stalker2-paks, stalker2-cfg, stalker2-gamedata, stalker2-curves, stalker2-localization, stalker2-saves |
| Testing and fixing | stalker2-testing (in-game console tests), stalker2-crashes |
| Zone Kit and assets | stalker2-zonekit, stalker2-blueprints, stalker2-mod-menus (in-game settings for a mod: the S2MM and MCM APIs), stalker2-animation, stalker2-audio, stalker2-voiceover |
| Shipping mods | stalker2-release, stalker2-vortex, stalker2-publish |

"core" = workflow, mod-setup, updates, paks, cfg, gamedata, testing, crashes, release, vortex.
Full descriptions: `python install.py --list` (or open any `skills/<name>/SKILL.md`).

## Install: pick one way

### A. The menu (Windows)
1. Unzip the pack anywhere, for example into your Downloads folder.
2. Open the unzipped folder `STALKER2-AI-Modding-Toolkit-1.0.0`.
3. Double-click `install.bat`. A black window opens with the list of skills.
4. Type `c` for the core skills, `a` for all of them, or numbers such as `1,3,5-7`, then press Enter.
5. It shows the AI agents it found on this PC. Press Enter to accept, or type the numbers you want and press Enter.
6. Type `u` and press Enter to install for every project (or `p` for one project folder).
7. Read the plan it prints. Nothing has changed yet. Type `y` and press Enter to install.
8. Close and reopen your AI agent (or start a new session) so it sees the new skills.

If the window says Python was not found: install Python 3 from python.org (tick "Add python.exe to PATH" on the
first installer page), then double-click `install.bat` again.

### B. Ask your AI agent
Open this folder in your agent and say: "Install the STALKER 2 skills from this folder; follow AGENTS.md." It will
list the skills, ask what you want, show the plan, and wait for your yes.

### C. By hand
Copy the folders you want from `skills/` into your agent's skills folder:

| Agent | Every project | One project |
|---|---|---|
| Claude Code | `%USERPROFILE%/.claude/skills/` | `<project>/.claude/skills/` |
| Codex, GitHub Copilot, Cursor, Gemini CLI, Windsurf, OpenCode, Goose, Amp, Junie | `%USERPROFILE%/.agents/skills/` | `<project>/.agents/skills/` |
| Kiro | `%USERPROFILE%/.kiro/skills/` | `<project>/.kiro/skills/` |
| Cline | `%USERPROFILE%/.cline/skills/` | `<project>/.cline/skills/` |
| Antigravity IDE | `%USERPROFILE%/.gemini/config/skills/` | `<project>/.agents/skills/` |
| claude.ai or Claude Desktop | upload the zips in `claude-ai/` (steps: `python install.py --claude-ai`) | |

Install each skill for one agent folder only. Some agents read more than one of these folders, and the same skill
twice can confuse them.

### Already have skills with the same names?
The installer never overwrites a skill it did not install; it says REFUSED and leaves yours alone. To try this pack
next to your own skills, install it for one project (`p` in the menu): in Claude Code a project skill takes
priority over a user skill of the same name, inside that project only.

## Tools you get yourself
None of these are included. The skills tell the agent when each is needed.

| Tool | Where to get it | Needed by |
|---|---|---|
| Python 3.8 or newer | python.org | every script |
| Python packages | `pip install cityhash` | package ids and IoStore redirects |
| retoc | github.com/trumank/retoc (Releases) | paks, Zone Kit packing, updates |
| repak | github.com/trumank/repak (Releases) | paks, cfg tables, updates |
| oo2core_9_win64.dll (Oodle) | copy it from your own Zone Kit: `<Zone Kit>/Engine/Binaries/DotNET/AutomationTool/oo2core_9_win64.dll` | put it next to retoc.exe and repak.exe |
| STALKER 2 Zone Kit | Epic Games Launcher | stalker2-zonekit and asset work |
| .NET 8 SDK | dotnet.microsoft.com | building uasset-dump (stalker2-zonekit/tools) |
| Node.js 24 or newer | nodejs.org | stalker2-cfg (run `npm install` in its scripts folder once) |
| A console mod of your choice (Kynes Commands Console works) | Nexus Mods (STALKER 2) | stalker2-testing |

Put retoc.exe, repak.exe and the Oodle DLL in one folder. The scripts find the game, the Zone Kit and ~mods by
themselves. To see what they found, or to set a path by hand:

    python <skills folder>/stalker2-updates/scripts/s2paths.py
    python <skills folder>/stalker2-updates/scripts/s2paths.py --set tools="<folder with retoc.exe>"

## Remove or check
    python install.py --uninstall all --agent claude-code
    python install.py --verify --agent claude-code

Uninstall removes only folders this pack installed. Backups of anything replaced are kept in
`%USERPROFILE%/.stalker2-skill-pack/backups/`.

## More
SECURITY.md (what the installer and scripts do), CREDITS.md, LICENSE, CHANGELOG.md.
