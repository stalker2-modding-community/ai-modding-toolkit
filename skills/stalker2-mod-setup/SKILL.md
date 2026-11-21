---
name: stalker2-mod-setup
description: "Learns the user's own STALKER 2 mods after the pack is installed: reads their repo or notes, or, if there are none, reads the mod's files, then builds a local git repo per mod and keeps it updated. Use right after installing the pack, at the start of a session in a folder with no MOD.md, when the user says 'learn my mod', or when work starts on a mod the agent has no notes for."
license: MIT
compatibility: Python 3.8+; git (optional but recommended); retoc and repak to list pak contents (see the pack START_HERE.md)
metadata:
  pack: STALKER 2 AI Modding Toolkit
  pack-version: "1.0.0"
  author: STALKER 2 AI Modding Toolkit contributors
  verified-on: "STALKER 2 Steam build 26123434 (game 2.1), Zone Kit 2.1.0"
---

# Learning the user's mods

Goal: know each mod the user works on as well as the user does, keep that knowledge in a local repo, and keep the repo
current. Ask one question at a time and wait for the answer.

## 1. Is there something to read?
Ask: "Do you have a repo, docs or notes for your mod or mods? If so, where?"
- **Yes**: read it (README, changelog, build scripts, cfg sources, release folders, any notes). Summarise the mod back in
  five to ten lines: what it does for the player, which files ship, which tables or assets it changes, its load priority,
  open issues. Ask the user to correct the summary. If it is not a git repo, offer step 3 for it.
- **No**: go to step 2.

## 2. Read the mod from its files
Ask where the mod is. Common places: the Vortex staging folder (by default `%APPDATA%/Vortex/stalker2heartofchornobyl/mods/`),
`<mods>`, a download zip, or the Zone Kit mod folder `<kit>/Stalker2/Mods/<Mod>/`.
1. `python scripts/mod_inventory.py <folder or .zip> --out <scratch>/inventory.md`: every file with its sha256, paks grouped
   into trios with their mount priority, what each pak holds, loose cfg, a FOMOD installer, readmes, Zone Kit source.
   Read-only on the input.
2. Read the content the inventory found. Read references/reading-a-mod.md before this step: it says which pack skill
   and command reads each kind of file (cfg patches, whole-file replacements, cooked assets, Blueprints, kit source).
3. Write the same summary as in step 1 and ask the user to confirm it. Ask what you could not tell from the files: the
   intent behind values, known bugs, what is tested.

## 3. Build a local repo for each mod
Ask where it should live; suggest `Documents/STALKER2 Mods/<ModName>/`. Then
`python scripts/init_mod_repo.py <folder> --name "<Mod name>" [--author "<name>"]`. It creates the layout below, runs `git init`
and makes the first commit. It never overwrites a file and never adds a remote. Pass `--with-hook` to install an opt-in
pre-commit hook running `scripts/mod_guardrail.py` (blocks secrets, nested `Content/Content/`, and dev dirs in `Content/`; warns on user-path leaks in notes/logs and unknown `Content/` files).

| Path | Holds |
|---|---|
| `MOD.md` | what the mod does, files and versions, what it changes, priority and conflicts, how it is built, known issues, last game build checked |
| `CHANGELOG.md` | one entry per version |
| `LOG.md` | each test build and the user's verdict in their own words |
| `source/` | the readable source: cfg patch files, generator scripts, kit asset backups |
| `release/<version>/` | exactly the files that shipped (the build identifier in stalker2-paks looks for this layout) |
| `baseline/` | vanilla extracts for update checks (git-ignored: it is GSC data) |
| `notes/` | anything else worth keeping |

Fill `MOD.md` from the confirmed summary, copy the current release into `release/<version>/`, commit.

## 4. Keep it updated
- At every session start on a mod: read `MOD.md` and `git log --oneline -15` before proposing anything.
- After each change the user approves: update `MOD.md` (and `CHANGELOG.md` for a release), add the build and verdict to
  `LOG.md`, commit with a plain message saying what changed and why.
- After a release: copy the shipped files to `release/<version>/` and commit (stalker2-release).
- After a game update: record what stalker2-updates found in `MOD.md` ("last game build checked") and commit.
- Show the user `git status` before committing when unsure what belongs in the commit.

## Rules
- Only the user's own mods, or mods whose author allows it. Another author's mod: note neutral compatibility facts in
  `MOD.md`; never copy its files or decoded content into a repo.
- Local only: never add a remote or push unless the user asks. Never commit secrets, logs with user names, or other
  people's files. Ask before committing large binaries other than release files.
- Do not change the mod's files while learning it: read only, work on copies in a scratch folder.
- No git installed: create the same layout as a plain folder and tell the user they can install Git for Windows later;
  `init_mod_repo.py --no-git` does that.
- Several mods: one repo per mod. Shared notes across mods go in the user's own notes, not in each repo.
